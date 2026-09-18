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
  assert.match(html, /Rank #1/);
  assert.match(html, /结合模式/);
  assert.match(html, /CCO/);
  assert.match(html, /0.610/);
  assert.match(html, /Lipinski PASS/);
  assert.match(html, /Not evaluated/);
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
  assert.match(html, /-6.80 kcal\/mol/);
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
  assert.match(html, /data-viewer-mode="ligand"/);
});

test("MoleculeViewer3D marks a protein-ligand complex when protein PDB is provided", async () => {
  const { MoleculeViewer3D } = await server.ssrLoadModule("/src/components/MoleculeViewer3D.tsx");
  const html = renderToStaticMarkup(React.createElement(MoleculeViewer3D, {
    molBlock: "mock mol block",
    proteinPdb: "ATOM mock protein",
    label: "候选分子 1 的蛋白-配体结合模式",
  }));

  assert.match(html, /data-viewer-mode="complex"/);
  assert.match(html, /蛋白-配体结合模式/);
});

test("AI Drug Discovery Pipeline renders all tools and their statuses as cards", async () => {
  const { DiscoveryPipeline } = await server.ssrLoadModule("/src/components/DiscoveryPipeline.tsx");
  const html = renderToStaticMarkup(React.createElement(DiscoveryPipeline, {
    tools: [
      { name: "esm2_encoding", status: "completed" },
      { name: "generate_molecules", status: "running" },
    ],
  }));

  assert.match(html, /AI Drug Discovery Pipeline/);
  assert.match(html, /ESM-2/);
  assert.match(html, /DLPS-E2PO/);
  assert.match(html, /RDKit/);
  assert.match(html, /Property Analyzer/);
  assert.match(html, /AutoDock Vina/);
  assert.match(html, /completed/);
  assert.match(html, /running/);
});

test("AI Analysis Report renders task counts and every best-candidate metric", async () => {
  const { AnalysisReportCard } = await server.ssrLoadModule("/src/components/AnalysisReportCard.tsx");
  const html = renderToStaticMarkup(React.createElement(AnalysisReportCard, {
    report: {
      target: "ESR1",
      generated: 5,
      validCandidates: 3,
      bestCandidate: {
        rank: 1, smiles: "CCN", valid: true, qed: 0.78, sa: 2.4,
        molwt: 315.4, logp: 2.1, lipinski: true, vina: -8.24,
        structure_svg: null, sdf: null,
      },
    },
  }));

  assert.match(html, /AI Analysis Report/);
  assert.match(html, /ESR1/);
  assert.match(html, /Generated/);
  assert.match(html, /Valid Candidates/);
  assert.match(html, /Best Candidate/);
  assert.match(html, /-8.24 kcal\/mol/);
  assert.match(html, /0.780/);
  assert.match(html, /2.400/);
  assert.match(html, /PASS/);
  assert.match(html, /315.4/);
  assert.match(html, /2.10/);
  assert.match(html, /Agent Evaluation/);
  assert.match(html, /Awaiting evaluation data/);
  assert.match(html, /N\/A/);
});

test("AI Analysis Report renders normalized Agent Evaluation progress metrics", async () => {
  const { AnalysisReportCard } = await server.ssrLoadModule("/src/components/AnalysisReportCard.tsx");
  const html = renderToStaticMarkup(React.createElement(AnalysisReportCard, {
    report: {
      target: "ESR1", generated: 1, validCandidates: 1,
      bestCandidate: {
        rank: 1, smiles: "CCN", valid: true, qed: 0.78, sa: 2.4,
        molwt: 315.4, logp: 2.1, lipinski: true, vina: -8.24,
        structure_svg: null, sdf: null,
      },
      evaluationReport: {
        intent_accuracy: 0.96,
        parameter_accuracy: 91,
        tool_calling_success: 0.875,
        task_success_rate: 100,
      },
    },
  }));

  assert.match(html, /Intent Accuracy/);
  assert.match(html, /Parameter Accuracy/);
  assert.match(html, /Tool Calling Success/);
  assert.match(html, /Task Success Rate/);
  assert.match(html, /96%/);
  assert.match(html, /91%/);
  assert.match(html, /87.5%/);
  assert.match(html, /100%/);
  assert.doesNotMatch(html, /Awaiting evaluation data/);
});
