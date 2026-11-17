import { requestJson } from "./httpClient";

export type FigureStatus = {
  task_id: string;
  candidate_index: number;
  state: "queued" | "pending" | "rendering" | "ready" | "unavailable" | "failed";
  image_url: string | null;
  palette_id: number | null;
  message: string | null;
};

export function figurePath(taskId: string, candidateIndex: number): string {
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(taskId) || !Number.isInteger(candidateIndex) || candidateIndex < 0) {
    throw new Error("无效的 Task ID 或候选索引");
  }
  return `/api/tasks/${encodeURIComponent(taskId)}/binding-figures/${candidateIndex}`;
}

export function getFigure(base: string, path: string, fetchImpl: typeof fetch = fetch) {
  return requestJson<FigureStatus>(base, path, {}, 30_000, fetchImpl);
}

export function renderFigure(base: string, path: string, paletteId?: number, fetchImpl: typeof fetch = fetch) {
  if (paletteId !== undefined && (!Number.isInteger(paletteId) || paletteId < 1 || paletteId > 12)) throw new Error("配色编号须为 1–12");
  return requestJson<FigureStatus>(base, `${path}/render`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(paletteId === undefined ? {} : { palette_id: paletteId }),
  }, 30_000, fetchImpl);
}
