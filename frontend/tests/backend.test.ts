import assert from "node:assert/strict";
import test from "node:test";

import { DEFAULT_AGENT_PLAN, normalizeAgentPlan } from "../src/agentPlan.ts";
import { EVALUATION_TIMEOUT_MS, evaluationPercent, loadAgentEvaluationReport } from "../src/agentEvaluation.ts";
import { agentToolStatusIcon, displayAgentTools } from "../src/agentTools.ts";
import { HEALTH_TIMEOUT_MS, checkBackendHealth } from "../src/backend.ts";
import { buildAnalysisReport, rankCandidates } from "../src/candidateRanking.ts";
import { createVerifiedDemoTask } from "../src/demo.ts";
import { normalizeEvaluationReport } from "../src/taskPolling.ts";
import type { Candidate } from "../src/types.ts";
import { candidateSdfContent, combinedCandidatesSdf } from "../src/utils/exports.ts";

test("health success selects the live RTX 3090 backend", async () => {
  let requestedUrl = "";
  const fetchMock: typeof fetch = async (input) => {
    requestedUrl = String(input);
    return new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const result = await checkBackendHealth("https://example.test/", fetchMock);

  assert.equal(result, "live");
  assert.equal(requestedUrl, "https://example.test/api/health");
  assert.equal(HEALTH_TIMEOUT_MS, 5_000);
});

test("health timeout selects Demo Mode without retrying the backend", async () => {
  let requests = 0;
  const fetchMock: typeof fetch = (_input, init) => {
    requests += 1;
    return new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
    });
  };

  const result = await checkBackendHealth("https://example.test", fetchMock, 5);

  assert.equal(result, "demo");
  assert.equal(requests, 1);
});

test("Demo Mode exposes verified SMILES with unavailable metrics marked as null", () => {
  const task = createVerifiedDemoTask("ESR1", 5, true);

  assert.equal(task.current_stage, "Demo / Precomputed Result");
  assert.equal(task.candidates.length, 5);
  assert.match(task.candidates[0].smiles, /[CNOS]/);
  assert.equal(task.candidates[0].qed, null);
  assert.equal(task.candidates[0].sa, null);
  assert.equal(task.candidates[0].vina, null);
  assert.match(task.summary ?? "", /未调用 RTX 3090、RDKit 或 Vina/);
  assert.match(task.summary ?? "", /并非针对当前所选靶点实时生成/);
  assert.equal(task.generated, null);
  assert.equal(task.valid, null);
});

test("Agent plan defaults are safe when the submit response omits plan", () => {
  const plan = normalizeAgentPlan(undefined);

  assert.deepEqual(
    { target: plan.target, num_samples: plan.num_samples, run_docking: plan.run_docking },
    { target: "", num_samples: 1, run_docking: false },
  );
  assert.equal(DEFAULT_AGENT_PLAN.run_docking, false);
});

test("Agent plan keeps supplied values while defaulting missing run_docking", () => {
  const plan = normalizeAgentPlan({ target: "ESR1", num_samples: 3 });

  assert.equal(plan.target, "ESR1");
  assert.equal(plan.num_samples, 3);
  assert.equal(plan.run_docking, false);
});

test("single candidate SDF download content is built from mol_block", () => {
  const content = candidateSdfContent({ rank: 1, mol_block: "molecule\r\n  RDKit\r\nM  END\r\n" } as Candidate);

  assert.equal(content, "molecule\n  RDKit\nM  END\n$$$$\n");
});

test("combined SDF includes every available mol_block exactly once", () => {
  const content = combinedCandidatesSdf([
    { rank: 1, mol_block: "first\nM  END" },
    { rank: 2, mol_block: null },
    { rank: 3, mol_block: "second\nM  END\n$$$$" },
  ] as Candidate[]);

  assert.equal(content, "first\nM  END\n$$$$\nsecond\nM  END\n$$$$\n");
  assert.equal(content.match(/\$\$\$\$/g)?.length, 2);
});

test("Agent Tools map backend names and statuses to the five display steps", () => {
  const tools = displayAgentTools([
    { name: "esm2_encoding", status: "completed" },
    { name: "generate_molecules", status: "running" },
    { name: "rdkit_validation", status: "failed" },
  ]);

  assert.deepEqual(tools.map((tool) => tool.name), [
    "ESM-2",
    "AP-MolDiff",
    "RDKit",
    "Property Analyzer",
    "AutoDock Vina",
  ]);
  // Absent backend state is unknown, not evidence that the tool is pending.
  assert.deepEqual(tools.map((tool) => tool.status), ["completed", "running", "failed", "unknown", "unknown"]);
  assert.deepEqual(tools.map((tool) => agentToolStatusIcon(tool.status)), ["✓", "⏳", "✗", "?", "?"]);
});

test("candidate ranking prioritizes Vina, then higher QED and lower SA without mutating input", () => {
  const candidates = [
    { rank: 8, smiles: "A", vina: -7.1, qed: 0.95, sa: 1.2 },
    { rank: 7, smiles: "B", vina: -8.2, qed: 0.55, sa: 3.4 },
    { rank: 6, smiles: "C", vina: null, qed: 0.92, sa: 3.1 },
    { rank: 5, smiles: "D", vina: null, qed: 0.92, sa: 2.2 },
  ] as Candidate[];

  const ranked = rankCandidates(candidates);

  assert.deepEqual(ranked.map((candidate) => candidate.smiles), ["B", "A", "D", "C"]);
  assert.deepEqual(ranked.map((candidate) => candidate.rank), [1, 2, 3, 4]);
  assert.deepEqual(candidates.map((candidate) => candidate.rank), [8, 7, 6, 5]);
});

test("analysis report uses the ranked best candidate and real generated count", () => {
  const ranked = rankCandidates([
    { rank: 2, smiles: "CCO", valid: true, vina: null, qed: 0.61, sa: 2.3 },
    { rank: 1, smiles: "CCN", valid: true, vina: -7.9, qed: 0.51, sa: 3.1 },
  ] as Candidate[]);
  const report = buildAnalysisReport({
    task_id: "task-1", target: "ESR1", status: "completed", progress: 100,
    current_stage: "completed", error: null, requested: 2, generated: 5,
    valid: 2, returned: 2, candidates: ranked, requested_by_agent: false,
    agent_plan: null, tool_trace: [], summary: null,
  }, ranked);

  assert.equal(report?.target, "ESR1");
  assert.equal(report?.generated, 5);
  assert.equal(report?.validCandidates, 2);
  assert.equal(report?.bestCandidate.smiles, "CCN");
});

test("Agent Evaluation accepts 0-1 and 0-100 metric scales", () => {
  const report = normalizeEvaluationReport({
    intent_accuracy: 0.94,
    parameter_accuracy: 87,
    tool_calling_success: null,
    task_success_rate: 1,
  });

  assert.equal(evaluationPercent(report?.intent_accuracy), 94);
  assert.equal(evaluationPercent(report?.parameter_accuracy), 87);
  assert.equal(evaluationPercent(report?.tool_calling_success), null);
  assert.equal(evaluationPercent(report?.task_success_rate), 100);
});

test("evaluation API returns a validated report from the live backend", async () => {
  let requestedUrl = "";
  const fetchMock: typeof fetch = async (input) => {
    requestedUrl = String(input);
    return new Response(JSON.stringify({
      intent_accuracy: 0.98,
      parameter_accuracy: 94.23,
      tool_calling_success: 1,
      task_success_rate: 96,
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  };

  const report = await loadAgentEvaluationReport("https://example.test/", fetchMock);

  assert.equal(requestedUrl, "https://example.test/api/evaluation/report");
  assert.deepEqual(report, {
    intent_accuracy: 0.98,
    parameter_accuracy: 94.23,
    tool_calling_success: 1,
    task_success_rate: 96,
  });
  assert.equal(EVALUATION_TIMEOUT_MS, 5_000);
});

test("evaluation API HTTP failure returns null without throwing", async () => {
  const fetchMock: typeof fetch = async () => new Response("Unavailable", { status: 503 });
  assert.equal(await loadAgentEvaluationReport("https://example.test", fetchMock), null);
});

test("evaluation API network failure returns null without throwing", async () => {
  const fetchMock: typeof fetch = async () => { throw new TypeError("network down"); };
  assert.equal(await loadAgentEvaluationReport("https://example.test", fetchMock), null);
});

test("evaluation API rejects missing or out-of-range fields", async () => {
  const fetchMock: typeof fetch = async () => new Response(JSON.stringify({
    intent_accuracy: 0.98,
    parameter_accuracy: 101,
    tool_calling_success: 1,
  }), { status: 200, headers: { "Content-Type": "application/json" } });
  assert.equal(await loadAgentEvaluationReport("https://example.test", fetchMock), null);
});

test("evaluation API timeout returns null without changing application mode", async () => {
  const fetchMock: typeof fetch = async (_input, init) => new Promise((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")));
  });
  assert.equal(await loadAgentEvaluationReport("https://example.test", fetchMock, 5), null);
});

test("startup evaluation report overrides the optional task-level compatibility field", () => {
  const ranked = rankCandidates([{ rank: 1, smiles: "CCO", valid: true, qed: 0.61, sa: 2.3 }] as Candidate[]);
  const startupReport = {
    intent_accuracy: 0.99,
    parameter_accuracy: 95,
    tool_calling_success: 0.97,
    task_success_rate: 94,
  };
  const report = buildAnalysisReport({
    task_id: "task-2", target: "ESR1", status: "completed", progress: 100,
    current_stage: "completed", error: null, requested: 1, generated: 1,
    valid: 1, returned: 1, candidates: ranked, requested_by_agent: false,
    agent_plan: null, evaluation_report: {
      intent_accuracy: 0.5, parameter_accuracy: 50, tool_calling_success: 0.5, task_success_rate: 50,
    }, tool_trace: [], summary: null,
  }, ranked, startupReport);

  assert.deepEqual(report?.evaluationReport, startupReport);
});
