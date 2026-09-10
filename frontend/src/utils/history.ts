import type { StoredTask, Task } from "../types";

const STORAGE_KEY = "drug-design-agent:recent-tasks:v1";
const MAX_HISTORY = 6;

export function loadHistory(): StoredTask[] {
  try {
    const value = localStorage.getItem(STORAGE_KEY);
    return value ? (JSON.parse(value) as StoredTask[]).slice(0, MAX_HISTORY) : [];
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
  localStorage.removeItem(STORAGE_KEY);
}
