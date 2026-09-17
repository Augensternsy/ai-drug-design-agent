import type { AgentPlan } from "./types";

export const DEFAULT_AGENT_PLAN: AgentPlan = {
  target: "",
  num_samples: 1,
  run_docking: false,
  qed_threshold: null,
  sa_threshold: null,
  qed_priority: false,
  dock_top_k: null,
  parser: "rules",
};

export function normalizeAgentPlan(plan?: Partial<AgentPlan> | null): AgentPlan {
  return {
    ...DEFAULT_AGENT_PLAN,
    ...plan,
    target: typeof plan?.target === "string" ? plan.target : DEFAULT_AGENT_PLAN.target,
    num_samples: typeof plan?.num_samples === "number" && Number.isFinite(plan.num_samples)
      ? Math.max(1, Math.trunc(plan.num_samples))
      : DEFAULT_AGENT_PLAN.num_samples,
    run_docking: typeof plan?.run_docking === "boolean" ? plan.run_docking : DEFAULT_AGENT_PLAN.run_docking,
  };
}
