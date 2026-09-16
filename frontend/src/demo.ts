import type { AgentPlan, Candidate, Task } from "./types";

const VERIFIED_MODEL_SMILES = [
  "COc1ccc(C(=O)OC[C@H]2CC[C@H](NS(=O)(=O)c3cccc(OC)n3)CC2)cc1",
  "CNC(=O)c1ccc2cc(NC)nc(Nc3cccc(Cl)c3C(N)=O)c2n1",
  "CN1CC(NC(=O)c2cc(-c3cccnc3CC(F)(F)F)nc(N)n2)C1",
  "Cc1ccc(-c2ccc(C(=O)N[C@H](C)c3ccccc3)cc2)cc1",
  "O=C(Nc1ccc(S(=O)(=O)N2CCCC2)cc1)c1ccccc1",
] as const;

const SUPPORTED_TARGETS = [
  "ESR1", "HCRTR1", "JAK1", "P2RX3", "KDM1A", "IDH1",
  "RIOK1", "NR4A1", "GRIK1", "CCR9", "FTO", "SPIN1",
] as const;

function candidateFromSmiles(smiles: string, index: number): Candidate {
  return {
    rank: index + 1,
    smiles,
    valid: true,
    qed: null,
    sa: null,
    molwt: null,
    logp: null,
    lipinski: null,
    vina: null,
    structure_svg: null,
    sdf: null,
  };
}

export function parseDemoPrompt(prompt: string): { target: string; count: number } {
  const upper = prompt.toUpperCase();
  const target = SUPPORTED_TARGETS.find((name) => upper.includes(name)) ?? "ESR1";
  const match = prompt.match(/(?:生成|设计|筛选)?\D{0,12}([1-5])\s*(?:个|条|molecules?|candidates?)/i);
  return { target, count: match ? Number(match[1]) : 1 };
}

export function createVerifiedDemoTask(
  target: string,
  count: number,
  requestedDocking: boolean,
  requestedByAgent = false,
): Task {
  const safeCount = Math.min(5, Math.max(1, Math.trunc(count)));
  const candidates = VERIFIED_MODEL_SMILES.slice(0, safeCount).map(candidateFromSmiles);
  const agentPlan: AgentPlan | null = requestedByAgent ? {
    target,
    num_samples: safeCount,
    qed_threshold: null,
    sa_threshold: null,
    qed_priority: true,
    run_docking: false,
    dock_top_k: null,
    parser: "rules",
  } : null;

  return {
    task_id: `demo-${target.toLowerCase()}-${Date.now()}`,
    target,
    status: "completed",
    progress: 100,
    current_stage: "Demo / Precomputed Result",
    error: null,
    requested: safeCount,
    generated: safeCount,
    valid: safeCount,
    returned: safeCount,
    candidates,
    requested_by_agent: requestedByAgent,
    agent_plan: agentPlan,
    tool_trace: [
      { name: "resolve_target", status: "completed", detail: `${target} · precomputed` },
      { name: "generate_molecules", status: "completed", detail: "Previously verified model SMILES" },
      { name: "evaluate_properties", status: "skipped", detail: "Metrics unavailable in the public demo dataset" },
      { name: "molecular_docking", status: "skipped", detail: requestedDocking ? "Demo Mode never runs Vina" : "Vina not requested" },
      { name: "rank_candidates", status: "completed", detail: "Preserved precomputed order" },
      { name: "generate_result_summary", status: "completed", detail: "Demo disclosure attached" },
    ],
    summary: `Demo / Precomputed Result：展示 ${safeCount} 个既有真实模型 SMILES；本次未调用 RTX 3090、RDKit 或 Vina，缺失指标显示 N/A。`,
  };
}
