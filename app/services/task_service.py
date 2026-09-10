"""Async task lifecycle built from reusable Agent Tool wrappers."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.agent.tools import (
    attach_molecular_assets,
    evaluate_properties,
    generate_molecules,
    molecular_docking,
    rank_candidates,
    resolve_target,
    summarize_results,
)
from app.schemas.api_models import (
    AgentPlan,
    CandidateMolecule,
    GenerateRequest,
    TaskStatusResponse,
)

logger = logging.getLogger(__name__)

_TASKS: Dict[str, Dict[str, Any]] = {}
TOOL_ORDER = [
    "resolve_target",
    "generate_molecules",
    "evaluate_properties",
    "molecular_docking",
    "rank_candidates",
    "generate_result_summary",
]


def _new_tool_trace(run_docking: bool) -> list[dict[str, str | None]]:
    return [
        {
            "name": name,
            "status": "pending" if name != "molecular_docking" or run_docking else "skipped",
            "detail": None,
        }
        for name in TOOL_ORDER
    ]


class TaskService:
    """Create, query, and execute molecule-generation tasks in memory."""

    @staticmethod
    def create_task(
        req: GenerateRequest,
        background_tasks: Any = None,
        agent_plan: AgentPlan | None = None,
        client_key: str | None = None,
    ) -> str:
        target = resolve_target(req.target)
        task_id = str(uuid.uuid4())
        _TASKS[task_id] = {
            "task_id": task_id,
            "target": target,
            "num_samples": req.num_samples,
            "qed_threshold": req.qed_threshold,
            "sa_threshold": req.sa_threshold,
            "run_docking": req.run_docking,
            "dock_top_k": req.dock_top_k,
            "status": "queued",
            "progress": 0.0,
            "current_stage": "Task queued",
            "error": None,
            "requested": req.num_samples,
            "generated": 0,
            "valid": 0,
            "returned": 0,
            "candidates": [],
            "requested_by_agent": agent_plan is not None,
            "agent_plan": agent_plan,
            "tool_trace": _new_tool_trace(req.run_docking),
            "summary": None,
            "client_key": client_key,
        }
        TaskService._set_tool(task_id, "resolve_target", "completed", target)
        if background_tasks is not None:
            background_tasks.add_task(TaskService._run_generation_task_sync, task_id)
        else:
            try:
                asyncio.get_running_loop().create_task(TaskService._run_generation_task(task_id))
            except RuntimeError:
                import threading

                threading.Thread(
                    target=lambda: asyncio.run(TaskService._run_generation_task(task_id)),
                    daemon=True,
                ).start()
        return task_id

    @staticmethod
    def _set_tool(task_id: str, name: str, status: str, detail: str | None = None) -> None:
        task = _TASKS.get(task_id)
        if not task:
            return
        for tool in task["tool_trace"]:
            if tool["name"] == name:
                tool["status"] = status
                tool["detail"] = detail
                return

    @staticmethod
    def _run_generation_task_sync(task_id: str) -> None:
        asyncio.run(TaskService._run_generation_task(task_id))

    @staticmethod
    def get_task(task_id: str) -> Optional[TaskStatusResponse]:
        task = _TASKS.get(task_id)
        if task is None:
            return None
        return TaskStatusResponse(
            task_id=task["task_id"],
            target=task["target"],
            status=task["status"],
            progress=task["progress"],
            current_stage=task["current_stage"],
            error=task["error"],
            num_samples=task["num_samples"],
            requested=task.get("requested", task["num_samples"]),
            generated=task.get("generated", 0),
            valid=task.get("valid", 0),
            returned=task.get("returned", len(task.get("candidates", []))),
            candidates=task["candidates"],
            requested_by_agent=task.get("requested_by_agent", False),
            agent_plan=task.get("agent_plan"),
            tool_trace=task.get("tool_trace", []),
            summary=task.get("summary"),
        )

    @staticmethod
    async def _run_generation_task(task_id: str) -> None:
        task = _TASKS.get(task_id)
        if not task:
            return

        target = task["target"]
        num_samples = task["num_samples"]
        run_docking = task["run_docking"]
        active_tool: str | None = None

        try:
            task.update(status="loading", progress=10.0, current_stage=f"Loading model and sequence for target {target}...")
            await asyncio.sleep(0)
            task.update(status="encoding", progress=25.0, current_stage="Encoding protein sequence with ESM-2...")

            active_tool = "generate_molecules"
            TaskService._set_tool(task_id, active_tool, "running")
            task.update(status="generating", progress=40.0, current_stage=f"Generating candidate molecules for target {target}...")

            valid_candidates: List[CandidateMolecule] = []
            total_generated = 0
            for attempt in range(1, 4):
                if len(valid_candidates) >= num_samples:
                    break
                needed = num_samples - len(valid_candidates)
                batch_size = max(needed, 2) if attempt > 1 else num_samples
                batch_smiles = await asyncio.to_thread(generate_molecules, target, batch_size)
                total_generated += len(batch_smiles)
                TaskService._set_tool(task_id, "generate_molecules", "completed", f"Generated {total_generated} raw samples")

                active_tool = "evaluate_properties"
                TaskService._set_tool(task_id, active_tool, "running")
                task.update(status="evaluating", progress=65.0, current_stage="Evaluating RDKit validity and molecular properties...")
                for smiles in batch_smiles:
                    evaluation = evaluate_properties(smiles)
                    if not evaluation["valid"]:
                        continue
                    if task["qed_threshold"] is not None and (evaluation["qed"] or 0) < task["qed_threshold"]:
                        continue
                    if task["sa_threshold"] is not None and (evaluation["sa"] or 10) > task["sa_threshold"]:
                        continue
                    if any(item.smiles == smiles for item in valid_candidates):
                        continue
                    valid_candidates.append(CandidateMolecule(
                        rank=len(valid_candidates) + 1,
                        smiles=smiles,
                        valid=True,
                        qed=evaluation.get("qed"),
                        sa=evaluation.get("sa"),
                        molwt=evaluation.get("molwt"),
                        logp=evaluation.get("logp"),
                        lipinski=evaluation.get("lipinski"),
                    ))
                    if len(valid_candidates) >= num_samples:
                        break

            evaluated = valid_candidates[:num_samples]
            task["generated"] = total_generated
            task["valid"] = len(evaluated)
            TaskService._set_tool(task_id, "evaluate_properties", "completed", f"{len(evaluated)} RDKit-valid candidates retained")

            docking_error: str | None = None
            if run_docking and evaluated:
                active_tool = "molecular_docking"
                TaskService._set_tool(task_id, active_tool, "running")
                task.update(status="docking", progress=80.0, current_stage="Performing AutoDock Vina molecular docking...")
                dock_candidates = sorted(evaluated, key=lambda item: item.qed if item.qed is not None else -1.0, reverse=True)
                if task["dock_top_k"]:
                    dock_candidates = dock_candidates[: task["dock_top_k"]]
                try:
                    dock_results = await asyncio.to_thread(molecular_docking, target, [item.smiles for item in dock_candidates])
                    dock_map = {result["smiles"]: result.get("vina_score") for result in dock_results}
                    errors = [result.get("error") for result in dock_results if not result.get("success") and result.get("error")]
                    for candidate in evaluated:
                        candidate.vina = dock_map.get(candidate.smiles)
                    docking_error = "; ".join(errors) if errors else None
                    TaskService._set_tool(
                        task_id,
                        "molecular_docking",
                        "completed" if any(item.vina is not None for item in evaluated) else "failed",
                        docking_error or f"Docked {len(dock_candidates)} candidate(s)",
                    )
                except Exception as exc:
                    docking_error = f"{type(exc).__name__}: {exc}"
                    logger.exception("Docking tool failed for task %s", task_id)
                    TaskService._set_tool(task_id, "molecular_docking", "failed", docking_error)

            active_tool = "rank_candidates"
            TaskService._set_tool(task_id, active_tool, "running")
            task.update(status="ranking", progress=92.0, current_stage="Ranking candidates and preparing molecular views...")
            ranked = rank_candidates(evaluated, run_docking)
            for candidate in ranked:
                await asyncio.to_thread(attach_molecular_assets, candidate)
            TaskService._set_tool(task_id, "rank_candidates", "completed")

            active_tool = "generate_result_summary"
            TaskService._set_tool(task_id, active_tool, "running")
            summary = summarize_results(target, ranked, run_docking)
            if docking_error:
                summary += f" 对接提示：{docking_error}"
            task.update(
                candidates=ranked,
                returned=len(ranked),
                summary=summary,
                status="completed",
                progress=100.0,
                current_stage=f"Completed with {len(ranked)} valid candidate(s).",
            )
            TaskService._set_tool(task_id, "generate_result_summary", "completed")
        except Exception as exc:
            logger.exception("Task %s failed", task_id)
            task.update(status="failed", progress=100.0, current_stage="Task failed", error=f"{type(exc).__name__}: {exc}")
            if active_tool:
                TaskService._set_tool(task_id, active_tool, "failed", str(exc))
