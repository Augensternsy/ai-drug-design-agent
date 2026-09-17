export type Candidate = {
  rank: number;
  smiles: string;
  valid: boolean;
  qed: number | null;
  sa: number | null;
  molwt: number | null;
  logp: number | null;
  lipinski: boolean | null;
  vina?: number | null;
  molecule_svg?: string;
  mol_block?: string | null;
  structure_svg: string | null;
  sdf: string | null;
};

export type AnalysisReport = {
  target: string;
  generated: number;
  bestCandidate: Candidate;
};

export type AgentPlan = {
  target: string;
  num_samples: number;
  qed_threshold: number | null;
  sa_threshold: number | null;
  qed_priority: boolean;
  run_docking: boolean;
  dock_top_k: number | null;
  parser: "rules" | "llm";
};

export type ToolExecution = {
  name: string;
  status: "pending" | "running" | "completed" | "skipped" | "failed";
  detail: string | null;
};

export type AgentTool = {
  name: string;
  status: string;
};

export type Task = {
  task_id: string;
  target: string;
  status: string;
  progress: number | null;
  current_stage: string;
  error: string | null;
  requested: number;
  generated: number | null;
  valid: number | null;
  returned: number | null;
  candidates: Candidate[];
  requested_by_agent: boolean;
  agent_plan: AgentPlan | null;
  tools?: AgentTool[];
  tool_trace: ToolExecution[];
  summary: string | null;
};

export type GenerateResponse = {
  task_id: string;
  status: string;
  message: string;
};

export type AgentGenerateResponse = GenerateResponse & { plan?: Partial<AgentPlan> | null };

export type StoredTask = {
  savedAt: string;
  task: Task;
};
