import type { AgentEvaluationReport, AnalysisReport, Candidate, Task } from "./types";

function finiteNumber(value: number | null | undefined): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function rankCandidates(candidates: Candidate[]): Candidate[] {
  return candidates
    .map((candidate, index) => ({ candidate, index }))
    .sort((left, right) => {
      if (left.candidate.valid !== right.candidate.valid) return left.candidate.valid ? -1 : 1;
      const leftVina = left.candidate.vina;
      const rightVina = right.candidate.vina;
      const leftHasVina = finiteNumber(leftVina);
      const rightHasVina = finiteNumber(rightVina);

      if (leftHasVina !== rightHasVina) return leftHasVina ? -1 : 1;
      if (leftHasVina && rightHasVina && leftVina !== rightVina) {
        return leftVina - rightVina;
      }

      const leftQed = finiteNumber(left.candidate.qed) ? left.candidate.qed : Number.NEGATIVE_INFINITY;
      const rightQed = finiteNumber(right.candidate.qed) ? right.candidate.qed : Number.NEGATIVE_INFINITY;
      if (leftQed !== rightQed) return rightQed - leftQed;

      const leftSa = finiteNumber(left.candidate.sa) ? left.candidate.sa : Number.POSITIVE_INFINITY;
      const rightSa = finiteNumber(right.candidate.sa) ? right.candidate.sa : Number.POSITIVE_INFINITY;
      if (leftSa !== rightSa) return leftSa - rightSa;

      return left.index - right.index;
    })
    .map(({ candidate }, index) => ({ ...candidate, rank: index + 1 }));
}

export function buildAnalysisReport(
  task: Task | null,
  rankedCandidates: Candidate[],
  startupEvaluationReport?: AgentEvaluationReport | null,
): AnalysisReport | null {
  const best = rankedCandidates.find(candidate => candidate.valid);
  if (!task || !["completed", "failed"].includes(task.status) || !best) return null;

  return {
    target: task.target,
    generated: task.generated,
    validCandidates: task.valid,
    partial: task.result_status === "partial" || task.status === "failed",
    bestCandidate: best,
    evaluationReport: startupEvaluationReport === undefined
      ? task.evaluation_report ?? null
      : startupEvaluationReport,
  };
}
