import assert from "node:assert/strict";
import test from "node:test";

import { DEFAULT_AGENT_PLAN, normalizeAgentPlan } from "../src/agentPlan.ts";
import { HEALTH_TIMEOUT_MS, checkBackendHealth } from "../src/backend.ts";
import { createVerifiedDemoTask } from "../src/demo.ts";

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
