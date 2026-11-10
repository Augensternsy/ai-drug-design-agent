import { requestJson } from "./httpClient";
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/+$/, "");

export function apiRequest<T>(path: string, options?: RequestInit, timeoutMs = 30_000): Promise<T> {
  return requestJson<T>(API_BASE_URL, path, options, timeoutMs);
}
