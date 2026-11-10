import type { StoredTask, Task } from "../types";
import { normalizeTaskResponse } from "../taskPolling";

const STORAGE_KEY = "drug-design-agent:recent-tasks:v1";
const MAX_HISTORY = 6;

export function loadHistory(): StoredTask[] {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    const parsed: unknown = value ? JSON.parse(value) : [];
    if (!Array.isArray(parsed)) return [];
    return parsed.slice(0, MAX_HISTORY).flatMap(item => {
      try { return [{ savedAt: String(item.savedAt ?? ""), task: normalizeTaskResponse(item.task) }]; }
      catch { return []; }
    });
  } catch {
    return [];
  }
}

export function saveTaskToHistory(task: Task): StoredTask[] {
  const next = [
    { savedAt: new Date().toISOString(), task },
    ...loadHistory().filter((item) => item.task.task_id !== task.task_id),
  ].slice(0, MAX_HISTORY);
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next.slice(0, 3)));
    } catch {
      // Storage may be unavailable in private mode; task viewing still works.
    }
  }
  return next;
}

export function clearHistory(): void {
  try { localStorage.removeItem(STORAGE_KEY); } catch { /* Storage disabled. */ }
}

const ACTIVE_KEY = "drug-design-agent:active-task:v1";
export function validTaskId(id: string): boolean { return /^[a-zA-Z0-9_-]{1,100}$/.test(id); }
export function loadActiveTask(baseUrl: string): string | null {
  try {
    const item = JSON.parse(localStorage.getItem(ACTIVE_KEY) ?? "null");
    return item?.baseUrl === baseUrl && typeof item.taskId === "string" && validTaskId(item.taskId) ? item.taskId : null;
  } catch { return null; }
}
export function saveActiveTask(baseUrl: string, taskId: string): void {
  if (!validTaskId(taskId)) return;
  try { localStorage.setItem(ACTIVE_KEY, JSON.stringify({ baseUrl, taskId })); } catch { /* No persistent storage available. */ }
}
export function clearActiveTask(baseUrl: string, taskId: string): void {
  try { if (loadActiveTask(baseUrl) === taskId) localStorage.removeItem(ACTIVE_KEY); } catch { /* Storage disabled. */ }
}
