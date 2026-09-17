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

test("MoleculeCard renders the backend molecule_svg in the real 2D view", async () => {
  const { MoleculeCard } = await server.ssrLoadModule("/src/components/MoleculeCard.tsx");
  const html = renderToStaticMarkup(React.createElement(MoleculeCard, {
    candidate: {
      rank: 1, smiles: "CCO", valid: true, qed: 0.61, sa: 2.3,
      molwt: 46.07, logp: -0.3, lipinski: true, vina: -6.8,
      molecule_svg: '<svg xmlns="http://www.w3.org/2000/svg"><circle cx="10" cy="10" r="5"/></svg>',
      structure_svg: null, sdf: null,
    },
  }));

  assert.match(html, /候选分子 1 的二维结构/);
  assert.match(html, /data:image\/svg\+xml/);
  assert.match(html, /缩小二维结构/);
  assert.match(html, /Vina/);
  assert.doesNotMatch(html, /二维结构暂不可用/);
});

test("MoleculeViewer3D accepts a mol_block for the interactive 3D view", async () => {
  const { MoleculeViewer3D } = await server.ssrLoadModule("/src/components/MoleculeViewer3D.tsx");
  const html = renderToStaticMarkup(React.createElement(MoleculeViewer3D, {
    molBlock: "mock mol block",
    label: "候选分子 1 的三维构象",
  }));

  assert.match(html, /molecule-viewer-3d/);
  assert.match(html, /候选分子 1 的三维构象/);
});
