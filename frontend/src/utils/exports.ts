import type { Candidate, Task } from "../types";

function downloadBlob(content: BlobPart, mime: string, filename: string) {
  const url = URL.createObjectURL(new Blob([content], { type: mime }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return `"${text.replace(/"/g, '""')}"`;
}

export function downloadCandidateSdf(candidate: Candidate) {
  if (candidate.sdf) downloadBlob(candidate.sdf, "chemical/x-mdl-sdfile", `candidate-${candidate.rank}.sdf`);
}

export function exportTaskJson(task: Task) {
  downloadBlob(JSON.stringify(task, null, 2), "application/json", `${task.target}-${task.task_id.slice(0, 8)}.json`);
}

export function exportTaskCsv(task: Task) {
  const header = ["rank", "smiles", "qed", "sa", "molwt", "logp", "lipinski", "vina"];
  const rows = task.candidates.map((item) => [item.rank, item.smiles, item.qed, item.sa, item.molwt, item.logp, item.lipinski, item.vina]);
  downloadBlob([header, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n"), "text/csv;charset=utf-8", `${task.target}-${task.task_id.slice(0, 8)}.csv`);
}

export function downloadAllSdf(task: Task) {
  const records = task.candidates.map((item) => item.sdf).filter(Boolean).join("");
  if (records) downloadBlob(records, "chemical/x-mdl-sdfile", `${task.target}-${task.task_id.slice(0, 8)}-candidates.sdf`);
}
