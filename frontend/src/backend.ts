export type BackendMode = "checking" | "live" | "demo";

export const HEALTH_TIMEOUT_MS = 5_000;

type HealthPayload = { status?: string };

export async function checkBackendHealth(
  baseUrl: string,
  fetchImpl: typeof fetch = fetch,
  timeoutMs = HEALTH_TIMEOUT_MS,
): Promise<Exclude<BackendMode, "checking">> {
  if (!baseUrl) return "demo";

  const normalizedBaseUrl = baseUrl.replace(/\/$/, "");
  const controller = new AbortController();
  const timeout = globalThis.setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetchImpl(`${normalizedBaseUrl}/api/health`, {
      method: "GET",
      headers: { Accept: "application/json" },
      signal: controller.signal,
    });
    if (!response.ok) return "demo";
    const payload = await response.json() as HealthPayload;
    return payload.status === "ok" ? "live" : "demo";
  } catch {
    return "demo";
  } finally {
    globalThis.clearTimeout(timeout);
  }
}
