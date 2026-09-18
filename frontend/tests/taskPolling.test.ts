import assert from "node:assert/strict";
import test from "node:test";

import { pollTaskUntilTerminal } from "../src/taskPolling.ts";
import type { Task } from "../src/types.ts";

function task(status: string, overrides: Partial<Task> = {}): Task {
  return {
    task_id: "task-123",
    target: "ESR1",
    status,
    progress: status === "completed" ? 100 : 40,
    current_stage: status,
    error: null,
    requested: 1,
    generated: status === "completed" ? 1 : null,
    valid: status === "completed" ? 1 : null,
    returned: status === "completed" ? 1 : null,
    candidates: [],
    requested_by_agent: false,
    agent_plan: null,
    tool_trace: [],
    summary: null,
    ...overrides,
  };
}

test("polls running -> running -> completed and returns candidates with the protein structure", async () => {
  const candidate = {
    rank: 1,
    smiles: "CCO",
    valid: true,
    qed: 0.61,
    sa: 2.3,
    molwt: 46.07,
    logp: -0.3,
    lipinski: true,
    vina: null,
    mol_block: "mock mol block",
    structure_svg: null,
    sdf: null,
  };
  const proteinPdb = "ATOM      1  N   ALA A   1      11.104  13.207   9.560  1.00 20.00           N";
  const responses = [task("running"), task("processing", { progress: 75 }), task("completed", { candidates: [candidate], protein_pdb: proteinPdb })];
  const updates: Task[] = [];
  const waits: number[] = [];

  const result = await pollTaskUntilTerminal("task-123", {
    fetchTask: async () => responses.shift()!,
    onUpdate: (nextTask) => updates.push(nextTask),
    sleep: async (milliseconds) => { waits.push(milliseconds); },
    now: (() => { let time = 0; return () => (time += 100); })(),
  });

  assert.deepEqual(updates.map((item) => item.status), ["running", "processing", "completed"]);
  assert.deepEqual(waits, [2_000, 2_000]);
  assert.equal(result.progress, 100);
  assert.equal(result.candidates[0].smiles, "CCO");
  assert.equal(result.candidates[0].mol_block, "mock mol block");
  assert.equal(result.protein_pdb, proteinPdb);
});

test("task polling preserves Agent Tools returned by the backend", async () => {
  const result = await pollTaskUntilTerminal("task-123", {
    fetchTask: async () => task("completed", { tools: [{ name: "esm2_encoding", status: "completed" }] }),
    onUpdate: () => undefined,
    sleep: async () => undefined,
  });

  assert.deepEqual(result.tools, [{ name: "esm2_encoding", status: "completed" }]);
});

test("task polling preserves the optional Agent Evaluation report", async () => {
  const evaluationReport = {
    intent_accuracy: 0.95,
    parameter_accuracy: 91,
    tool_calling_success: 0.88,
    task_success_rate: 84,
  };
  const result = await pollTaskUntilTerminal("task-123", {
    fetchTask: async () => task("completed", { evaluation_report: evaluationReport }),
    onUpdate: () => undefined,
    sleep: async () => undefined,
  });

  assert.deepEqual(result.evaluation_report, evaluationReport);
});

test("failed task stops polling and preserves backend error", async () => {
  let requests = 0;
  const result = await pollTaskUntilTerminal("task-123", {
    fetchTask: async () => {
      requests += 1;
      return task("failed", { error: "Vina failed" });
    },
    onUpdate: () => undefined,
    sleep: async () => undefined,
  });

  assert.equal(requests, 1);
  assert.equal(result.status, "failed");
  assert.equal(result.error, "Vina failed");
});

test("stops waiting after the two minute polling limit", async () => {
  let requests = 0;
  const times = [0, 0, 0, 120_000];

  await assert.rejects(() => pollTaskUntilTerminal("task-123", {
    fetchTask: async () => {
      requests += 1;
      return task("running");
    },
    onUpdate: () => undefined,
    sleep: async () => undefined,
    now: () => times.shift() ?? 120_000,
  }), /超过 2 分钟/);

  assert.equal(requests, 1);
});
