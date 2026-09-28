"""
Agent Evaluation Framework — Evaluates natural language task understanding,
parameter parsing, tool calling workflow, and end-to-end task execution.
"""
import sys
import os
import re
import json
import time
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.api_models import GenerateRequest
from app.services.task_service import TaskService
from app.services.target_service import TargetRegistry
from app.agent.parser import AgentIntentParser, parse_agent_intent_and_params

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("evaluate_agent")


def run_evaluation():
    test_cases_file = PROJECT_ROOT / "evaluation" / "test_cases.json"
    if not test_cases_file.exists():
        logger.error(f"Test cases file {test_cases_file} not found.")
        return

    with open(test_cases_file, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    total_cases = len(test_cases)
    logger.info(f"Loaded {total_cases} benchmark test cases from test_cases.json")

    correct_intent_count = 0
    correct_param_count = 0
    executed_tasks = 0
    tool_success_tasks = 0
    task_success_count = 0

    evaluated_case_results = []

    # Representative sample indices for live E2E verification
    sample_e2e_indices = {0, 2, 5, 10, 20}

    for idx, tc in enumerate(test_cases):
        user_input = tc["input"]
        expected = tc["expected"]

        # Parse Intent & Parameters
        parsed = parse_agent_intent_and_params(user_input)

        intent_correct = (parsed["target"] == expected["target"])
        param_correct = (
            parsed["num_samples"] == expected["num_samples"] and
            parsed["run_docking"] == expected["run_docking"]
        )

        if intent_correct:
            correct_intent_count += 1
        if param_correct:
            correct_param_count += 1

        case_eval = {
            "id": tc["id"],
            "input": user_input,
            "expected": expected,
            "parsed": parsed,
            "intent_correct": intent_correct,
            "param_correct": param_correct,
            "execution": None
        }

        if idx in sample_e2e_indices:
            executed_tasks += 1
            req = GenerateRequest(
                target=parsed["target"],
                num_samples=parsed["num_samples"],
                run_docking=parsed["run_docking"]
            )
            task_id = TaskService.create_task(req)

            # Poll for completion (up to 90s for GPU generation + Vina docking map calculation)
            max_poll = 180
            poll_cnt = 0
            task_res = None
            while poll_cnt < max_poll:
                time.sleep(0.5)
                poll_cnt += 1
                task_res = TaskService.get_task(task_id)
                if task_res and task_res.status in ("completed", "failed"):
                    break

            # Re-fetch final task status after polling loop finishes
            task_res = TaskService.get_task(task_id)
            if task_res:
                tool_map = {t.name: t.status for t in task_res.tools}
                expected_tools = ["ESM-2 Protein Encoding", "DLPS-E2PO Generation", "RDKit Validation", "Property Evaluation"]
                if parsed["run_docking"]:
                    expected_tools.append("AutoDock Vina Docking")
                tools_passed = (task_res.status == "completed") and all(tool_map.get(tn) == "completed" for tn in expected_tools)
                logger.info(f"Case {tc['id']} ({parsed['target']}): status={task_res.status}, error={task_res.error}, tools_passed={tools_passed}, tool_map={tool_map}")
                if tools_passed:
                    tool_success_tasks += 1

                # Verify Task Success
                if task_res.returned >= 1 and len(task_res.candidates) >= 1:
                    first_cand = task_res.candidates[0]
                    if first_cand.molecule_svg and first_cand.mol_block:
                        task_success_count += 1

                case_eval["execution"] = {
                    "task_id": task_id,
                    "status": task_res.status,
                    "returned": task_res.returned,
                    "tools_passed": tools_passed,
                    "candidates_count": len(task_res.candidates)
                }

        evaluated_case_results.append(case_eval)

    # Calculate Metric Metrics
    intent_accuracy = (correct_intent_count / total_cases) * 100.0
    param_accuracy = (correct_param_count / total_cases) * 100.0
    tool_success_rate = (tool_success_tasks / executed_tasks * 100.0) if executed_tasks > 0 else 0.0
    task_success_rate = (task_success_count / executed_tasks * 100.0) if executed_tasks > 0 else 0.0

    report = {
        "summary": {
            "total_cases": total_cases,
            "correct_intent": correct_intent_count,
            "intent_accuracy": round(intent_accuracy, 2),
            "correct_params": correct_param_count,
            "param_accuracy": round(param_accuracy, 2),
            "executed_tasks": executed_tasks,
            "tool_success_tasks": tool_success_tasks,
            "tool_success_rate": round(tool_success_rate, 2),
            "task_success_count": task_success_count,
            "task_success_rate": round(task_success_rate, 2)
        },
        "cases": evaluated_case_results
    }

    # Save JSON report
    report_json_path = PROJECT_ROOT / "evaluation" / "evaluation_report.json"
    with open(report_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Save Markdown report
    report_md_path = PROJECT_ROOT / "evaluation" / "evaluation_report.md"
    md_content = f"""# Agent Evaluation Benchmark Report

## 📊 Summary Metrics

| Metric | Value | Percentage |
| :--- | :--- | :--- |
| **Total Test Cases** | {total_cases} | 100% |
| **Correct Intent (Target Recognition)** | {correct_intent_count} / {total_cases} | **{intent_accuracy:.2f}%** |
| **Parameter Accuracy (Samples & Docking)** | {correct_param_count} / {total_cases} | **{param_accuracy:.2f}%** |
| **Executed E2E Sample Tasks** | {executed_tasks} | 100% |
| **Tool Success Rate (All Tools Completed)** | {tool_success_tasks} / {executed_tasks} | **{tool_success_rate:.2f}%** |
| **Task Success Rate (Valid Candidates Returned)** | {task_success_count} / {executed_tasks} | **{task_success_rate:.2f}%** |

---

## 🛠 Tool Calling Workflow Evaluation

The following 5 agent tools are verified for execution integrity during evaluation:
1. **ESM-2 Protein Encoding** — Contextual residue embedding
2. **DLPS-E2PO Generation** — Discrete token diffusion sampling
3. **RDKit Validation** — Molecular topology & kekulization verification
4. **Property Evaluation** — QED, SA score, Lipinski, 2D SVG, 3D MolBlock computation
5. **AutoDock Vina Docking** — 3D binding affinity calculation

---

## 📝 Test Cases Sample Results

| Case ID | Input Prompt | Expected Target | Parsed Target | Intent Match | Param Match | E2E Status |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: |
"""
    for item in evaluated_case_results[:15]:
        exp_tg = item["expected"]["target"]
        prs_tg = item["parsed"]["target"]
        intent_m = "✅" if item["intent_correct"] else "❌"
        param_m = "✅" if item["param_correct"] else "❌"
        e2e_st = item["execution"]["status"] if item.get("execution") else "N/A"
        md_content += f"| `{item['id']}` | {item['input']} | {exp_tg} | {prs_tg} | {intent_m} | {param_m} | `{e2e_st}` |\n"

    with open(report_md_path, "w", encoding="utf-8") as f:
        f.write(md_content)

    print("\n" + "=" * 60)
    print(" 🚀 AGENT EVALUATION COMPLETE ")
    print("=" * 60)
    print(f" Total Cases:             {total_cases}")
    print(f" Correct Intent (Target): {correct_intent_count} ({intent_accuracy:.2f}%)")
    print(f" Parameter Accuracy:      {correct_param_count} ({param_accuracy:.2f}%)")
    print(f" Tool Success Rate:       {tool_success_tasks}/{executed_tasks} ({tool_success_rate:.2f}%)")
    print(f" Task Success Rate:       {task_success_count}/{executed_tasks} ({task_success_rate:.2f}%)")
    print("=" * 60)
    print(f" JSON Report: {report_json_path}")
    print(f" Markdown Report: {report_md_path}\n")


if __name__ == "__main__":
    run_evaluation()
