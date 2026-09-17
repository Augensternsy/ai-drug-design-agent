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

function molBlockToSdfRecord(molBlock: string): string | null {
  const normalized = molBlock.replace(/\r\n?/g, "\n").trimEnd();
  if (!normalized.trim()) return null;
  const withoutExistingDelimiter = normalized.replace(/(?:\n)?\$\$\$\$$/, "").trimEnd();
  return `${withoutExistingDelimiter}\n$$$$\n`;
}

export function candidateSdfContent(candidate: Candidate): string | null {
  return candidate.mol_block ? molBlockToSdfRecord(candidate.mol_block) : null;
}

export function combinedCandidatesSdf(candidates: Candidate[]): string {
  return candidates.map(candidateSdfContent).filter((record): record is string => record !== null).join("");
}

export function downloadCandidateSdf(candidate: Candidate): boolean {
  const content = candidateSdfContent(candidate);
  if (!content) return false;
  downloadBlob(content, "chemical/x-mdl-sdfile;charset=utf-8", `candidate-${candidate.rank}.sdf`);
  return true;
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
  const content = combinedCandidatesSdf(task.candidates);
  if (content) downloadBlob(content, "chemical/x-mdl-sdfile;charset=utf-8", "combined_candidates.sdf");
}
