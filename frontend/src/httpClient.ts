export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

export async function requestJson<T>(base: string, path: string, options: RequestInit = {}, timeoutMs = 30_000, fetchImpl = fetch): Promise<T> {
  if (!base) throw new Error("未配置 API Base URL。");
  const controller = new AbortController();
  const abort = () => controller.abort(options.signal?.reason);
  if (options.signal?.aborted) abort();
  options.signal?.addEventListener("abort", abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, timeoutMs);
  try {
    const response = await fetchImpl(`${base.replace(/\/+$/, "")}${path}`, { ...options, signal: controller.signal });
    if (!response.ok) {
      const raw = await response.text();
      let detail = raw.slice(0, 500) || response.statusText;
      try {
        const body = JSON.parse(raw);
        detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
      } catch { /* Plain-text proxy/CORS error. */ }
      const labels: Record<number, string> = { 404: "任务或接口不存在（404）", 405: "请求方法不被支持（405）", 422: "参数校验失败（422）", 429: "请求过于频繁（429）", 503: "服务或任务存储暂不可用（503）" };
      throw new ApiError(response.status, `${labels[response.status] ?? `HTTP ${response.status}`}：${detail}`);
    }
    return await response.json() as T;
  } catch (error) {
    if (options.signal?.aborted) throw new DOMException("请求已取消", "AbortError");
    if (timedOut) throw new Error("请求超时；这不代表后端任务失败。请查询原任务，不要重复提交。");
    if (error instanceof TypeError) throw new Error("网络连接失败；任务状态未知，请查询原任务。");
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abort);
  }
}
