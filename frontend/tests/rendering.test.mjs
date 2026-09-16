import assert from "node:assert/strict";
import test, { after } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const server = await createServer({ server: { middlewareMode: true }, appType: "custom", logLevel: "silent" });
after(async () => server.close());

test("running task renders the loading UI with real progress fields", async () => {
  const { TaskLoadingCard } = await server.ssrLoadModule("/src/components/TaskLoadingCard.tsx");
  const html = renderToStaticMarkup(React.createElement(TaskLoadingCard, {
    task: {
      task_id: "task-123", target: "ESR1", status: "running", progress: 42,
      current_stage: "DLPS-E2PO inference", error: null, requested: 1,
      generated: null, valid: null, returned: null, candidates: [],
      requested_by_agent: false, agent_plan: null, tool_trace: [], summary: null,
    },
  }));

  assert.match(html, /正在生成候选分子/);
  assert.match(html, /DLPS-E2PO inference/);
  assert.match(html, /42%/);
  assert.doesNotMatch(html, /生成<\/span><strong>0/);
});

test("completed candidate renders a MoleculeCard without refresh", async () => {
  const { MoleculeCard } = await server.ssrLoadModule("/src/components/MoleculeCard.tsx");
  const html = renderToStaticMarkup(React.createElement(MoleculeCard, {
    candidate: {
      rank: 1, smiles: "CCO", valid: true, qed: 0.61, sa: 2.3,
      molwt: 46.07, logp: -0.3, lipinski: true, vina: null,
      structure_svg: null, sdf: null,
    },
  }));

  assert.match(html, /候选分子/);
  assert.match(html, /CCO/);
  assert.match(html, /0.610/);
  assert.match(html, /Lipinski PASS/);
});
