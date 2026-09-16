import type { Candidate, Task, ToolExecution } from "./types";

export const TASK_POLL_INTERVAL_MS = 2_000;
export const TASK_POLL_TIMEOUT_MS = 120_000;

type PollOptions = {
  fetchTask: (taskId: string) => Promise<unknown>;
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
    task_id: taskId,
    target: typeof payload.target === "string" ? payload.target : fallback?.target ?? "",
    status,
    progress,
    current_stage: typeof payload.current_stage === "string" ? payload.current_stage : fallback?.current_stage ?? "",
    error: typeof payload.error === "string" ? payload.error : null,
    requested: finiteNumber(payload.requested) ?? fallback?.requested ?? candidates.length,
    generated: finiteNumber(payload.generated) ?? fallback?.generated ?? null,
    valid: finiteNumber(payload.valid) ?? fallback?.valid ?? null,
    returned: finiteNumber(payload.returned) ?? fallback?.returned ?? null,
    candidates,
    requested_by_agent: typeof payload.requested_by_agent === "boolean" ? payload.requested_by_agent : fallback?.requested_by_agent ?? false,
    agent_plan: payload.agent_plan && typeof payload.agent_plan === "object" ? payload.agent_plan as Task["agent_plan"] : fallback?.agent_plan ?? null,
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
    const timer = globalThis.setTimeout(resolve, milliseconds);
    signal?.addEventListener("abort", () => {
      globalThis.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
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
    if (now() - startedAt >= timeoutMs) throw new Error("任务等待超过 2 分钟，请稍后查看任务历史或重新提交。");

    try {
      const task = normalizeTaskResponse(await options.fetchTask(taskId), fallback);
      fallback = task;
      options.onUpdate(task);
      if (task.status === "completed" || task.status === "failed") return task;
    } catch (error) {
      if (options.signal?.aborted || (error instanceof DOMException && error.name === "AbortError")) throw error;
      options.onTransientError?.(error);
    }

    if (now() - startedAt >= timeoutMs) throw new Error("任务等待超过 2 分钟，请稍后查看任务历史或重新提交。");
    await sleep(intervalMs, options.signal);
  }
}
