import type { AgentEvaluationReport } from "./types";

export const EVALUATION_TIMEOUT_MS = 5_000;

const EVALUATION_FIELDS = [
  "intent_accuracy",
  "parameter_accuracy",
  "tool_calling_success",
  "task_success_rate",
] as const;

export function validateEvaluationReport(value: unknown): AgentEvaluationReport | null {
  if (!value || typeof value !== "object") return null;
  const payload = value as Record<string, unknown>;
  for (const field of EVALUATION_FIELDS) {
    const metric = payload[field];
    if (typeof metric !== "number" || !Number.isFinite(metric) || metric < 0 || metric > 100) return null;
  }
  return {
    intent_accuracy: payload.intent_accuracy as number,
    parameter_accuracy: payload.parameter_accuracy as number,
    tool_calling_success: payload.tool_calling_success as number,
    task_success_rate: payload.task_success_rate as number,
  };
}

export async function loadAgentEvaluationReport(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
  timeoutMs = EVALUATION_TIMEOUT_MS,
): Promise<AgentEvaluationReport | null> {
  if (!baseUrl) return null;
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetchImpl(`${baseUrl.replace(/\/$/, "")}/api/evaluation/report`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) return null;
    return validateEvaluationReport(await response.json());
  } catch {
    return null;
  } finally {
    globalThis.clearTimeout(timeout);
  }
}

export function evaluationPercent(value: number | null | undefined): number | null {
  if (value == null || !Number.isFinite(value) || value < 0 || value > 100) return null;
  const percentage = value <= 1 ? value * 100 : value;
  return Math.round(percentage * 10) / 10;
}
