export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("当前为 Demo UI：请配置 VITE_API_BASE_URL 后再提交在线任务。");
  }

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, options);
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      try {
        const body = await response.json();
        detail = body.detail ?? detail;
      } catch {
        // Preserve the HTTP status for non-JSON gateway responses.
      }
      if (response.status === 429) {
        throw new Error(`提交过于频繁：${detail}`);
      }
      if (response.status >= 500) {
        throw new Error(`GPU 服务正在冷启动或暂时不可用，请稍后重试。(${detail})`);
      }
      throw new Error(detail);
    }
    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof TypeError) {
      throw new Error("无法连接 GPU API。可能正在冷启动，请稍后重试并保持页面开启。");
    }
    throw error;
  }
}
