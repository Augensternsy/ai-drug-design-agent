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

test("polls running -> running -> completed and returns candidates", async () => {
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
    structure_svg: null,
    sdf: null,
  };
  const responses = [task("running"), task("processing", { progress: 75 }), task("completed", { candidates: [candidate] })];
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
