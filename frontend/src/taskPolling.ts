import type { AgentEvaluationReport, AgentPlan, AgentTool, Candidate, Task, ToolExecution } from "./types";

export const TASK_POLL_INTERVAL_MS = 2_000;
export const TASK_POLL_TIMEOUT_MS = 120_000;

type PollOptions = {
  fetchTask: (taskId: string, signal: AbortSignal, timeoutMs: number) => Promise<unknown>;
  onUpdate: (task: Task) => void;
  initialTask?: Task;
  signal?: AbortSignal;
  intervalMs?: number;
  timeoutMs?: number;
  sleep?: (milliseconds: number, signal?: AbortSignal) => Promise<void>;
  now?: () => number;
  onTransientError?: (error: unknown) => void;
};

function finiteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function nullableBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null;
}

export function normalizeEvaluationReport(value: unknown): AgentEvaluationReport | null {
  if (!value || typeof value !== "object") return null;
  const report = value as Record<string, unknown>;
  return {
    intent_accuracy: finiteNumber(report.intent_accuracy),
    parameter_accuracy: finiteNumber(report.parameter_accuracy),
    tool_calling_success: finiteNumber(report.tool_calling_success),
    task_success_rate: finiteNumber(report.task_success_rate),
  };
}

function normalizeCandidate(value: unknown, index: number): Candidate | null {
  if (!value || typeof value !== "object") return null;
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.smiles !== "string" || !candidate.smiles.trim()) return null;
  return {
    rank: finiteNumber(candidate.rank) ?? index + 1,
    smiles: candidate.smiles,
    valid: candidate.valid === true,
    qed: finiteNumber(candidate.qed),
    sa: finiteNumber(candidate.sa),
    molwt: finiteNumber(candidate.molwt),
    logp: finiteNumber(candidate.logp),
    lipinski: nullableBoolean(candidate.lipinski),
    vina: finiteNumber(candidate.vina),
    vina_source: typeof candidate.vina_source === "string" ? candidate.vina_source : null,
    molecule_svg: typeof candidate.molecule_svg === "string" ? candidate.molecule_svg : undefined,
    mol_block: typeof candidate.mol_block === "string" ? candidate.mol_block : undefined,
    structure_svg: typeof candidate.structure_svg === "string" ? candidate.structure_svg : null,
    sdf: typeof candidate.sdf === "string" ? candidate.sdf : null,
  };
}

function normalizeTools(value: unknown): ToolExecution[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is ToolExecution => (
    !!item && typeof item === "object" && typeof (item as ToolExecution).name === "string"
  ));
}

function normalizeAgentTools(value: unknown): AgentTool[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const tool = item as Record<string, unknown>;
    return typeof tool.name === "string" && typeof tool.status === "string"
      ? [{ name: tool.name, status: tool.status.toLowerCase() }]
      : [];
  });
}

function normalizeTaskPlan(payload: Record<string, unknown>, fallback?: Task): AgentPlan | null {
  const source = payload.agent_plan && typeof payload.agent_plan === "object" ? payload.agent_plan
    : payload.parsed_plan && typeof payload.parsed_plan === "object" ? payload.parsed_plan : null;
  if (!source || Array.isArray(source)) return fallback?.agent_plan ?? null;
  const plan = source as Record<string, unknown>;
  const parser = plan.parser === "llm" || plan.parser === "rules" ? plan.parser
    : payload.parser_mode === "llm" ? "llm" : "rules";
  return {
    target: typeof plan.target === "string" ? plan.target : fallback?.agent_plan?.target ?? "",
    num_samples: finiteNumber(plan.num_samples) ?? fallback?.agent_plan?.num_samples ?? 1,
    qed_threshold: finiteNumber(plan.qed_threshold),
    sa_threshold: finiteNumber(plan.sa_threshold),
    qed_priority: typeof plan.qed_priority === "boolean" ? plan.qed_priority : false,
    run_docking: typeof plan.run_docking === "boolean" ? plan.run_docking : false,
    dock_top_k: finiteNumber(plan.dock_top_k),
    parser,
  };
}

export function normalizeTaskResponse(value: unknown, fallback?: Task): Task {
  if (!value || typeof value !== "object") throw new Error("任务状态响应格式无效。");
  const payload = value as Record<string, unknown>;
  const status = typeof payload.status === "string" ? payload.status.toLowerCase() : fallback?.status;
  const taskId = typeof payload.task_id === "string" ? payload.task_id : fallback?.task_id;
  if (!status || !taskId) throw new Error("任务状态响应缺少 status 或 task_id。");
  const candidates = Array.isArray(payload.candidates)
    ? payload.candidates.map(normalizeCandidate).filter((item): item is Candidate => item !== null)
    : fallback?.candidates ?? [];
  const progress = status === "completed" ? 100 : finiteNumber(payload.progress) ?? fallback?.progress ?? null;

  return {
    result_status: ["none", "complete", "partial"].includes(String(payload.result_status)) ? payload.result_status as Task["result_status"] : undefined,
    data_origin: typeof payload.data_origin === "string" ? payload.data_origin : undefined,
    task_id: taskId,
    parser_mode: payload.parser_mode === "rules" || payload.parser_mode === "llm" ? payload.parser_mode : fallback?.parser_mode,
    target: typeof payload.target === "string" ? payload.target : fallback?.target ?? "",
    protein_pdb: typeof payload.protein_pdb === "string" ? payload.protein_pdb : fallback?.protein_pdb ?? null,
    status,
    progress,
    current_stage: typeof payload.current_stage === "string" ? payload.current_stage : fallback?.current_stage ?? "",
    error: typeof payload.error === "string" ? payload.error : null,
    requested: finiteNumber(payload.requested) ?? fallback?.requested ?? 0,
    generated: finiteNumber(payload.generated) ?? fallback?.generated ?? null,
    valid: finiteNumber(payload.valid) ?? fallback?.valid ?? null,
    returned: finiteNumber(payload.returned) ?? fallback?.returned ?? null,
    candidates,
    requested_by_agent: typeof payload.requested_by_agent === "boolean" ? payload.requested_by_agent : fallback?.requested_by_agent ?? false,
    agent_plan: normalizeTaskPlan(payload, fallback),
    evaluation_report: payload.evaluation_report !== undefined ? normalizeEvaluationReport(payload.evaluation_report) : fallback?.evaluation_report ?? null,
    tools: Array.isArray(payload.tools) ? normalizeAgentTools(payload.tools) : fallback?.tools,
    tool_trace: Array.isArray(payload.tool_trace) ? normalizeTools(payload.tool_trace) : fallback?.tool_trace ?? [],
    summary: typeof payload.summary === "string" ? payload.summary : fallback?.summary ?? null,
  };
}

function defaultSleep(milliseconds: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("Aborted", "AbortError"));
      return;
    }
    const cleanup = () => signal?.removeEventListener("abort", abort);
    const timer = globalThis.setTimeout(() => { cleanup(); resolve(); }, milliseconds);
    const abort = () => {
      globalThis.clearTimeout(timer);
      cleanup();
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal?.addEventListener("abort", abort, { once: true });
  });
}

export async function pollTaskUntilTerminal(taskId: string, options: PollOptions): Promise<Task> {
  const intervalMs = options.intervalMs ?? TASK_POLL_INTERVAL_MS;
  const timeoutMs = options.timeoutMs ?? TASK_POLL_TIMEOUT_MS;
  const sleep = options.sleep ?? defaultSleep;
  const now = options.now ?? Date.now;
  const startedAt = now();
  let fallback = options.initialTask;

  while (true) {
    if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    if (now() - startedAt >= timeoutMs) throw new Error("任务等待超过 2 分钟；已暂停查询，后端状态未判失败。请继续查询原任务。");

    const controller = new AbortController();
    const cancel = () => controller.abort();
    options.signal?.addEventListener("abort", cancel, { once: true });
    const remaining = Math.min(30_000, Math.max(1, timeoutMs - (now() - startedAt)));
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const deadline = new Promise<never>((_, reject) => {
        timer = setTimeout(() => { reject(new Error("状态请求超时，继续查询原任务。")); controller.abort(); }, remaining);
        controller.signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
      });
      const task = normalizeTaskResponse(await Promise.race([options.fetchTask(taskId, controller.signal, remaining), deadline]), fallback);
      if (task.task_id !== taskId) throw new Error("响应任务 ID 不匹配。");
      fallback = task;
      options.onUpdate(task);
      if (task.status === "completed" || task.status === "failed") return task;
    } catch (error) {
      if (options.signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) throw error;
      if (error && typeof error === "object" && "status" in error && [400, 404, 405, 422].includes(Number(error.status))) throw error;
      options.onTransientError?.(error);
    } finally {
      clearTimeout(timer);
      options.signal?.removeEventListener("abort", cancel);
    }

    if (now() - startedAt >= timeoutMs) throw new Error("任务等待超过 2 分钟；后端状态未知，请继续查询原任务。");
    await sleep(Math.min(intervalMs, Math.max(0, timeoutMs - (now() - startedAt))), options.signal);
  }
}
