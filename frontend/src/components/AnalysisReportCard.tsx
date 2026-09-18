import type { AnalysisReport } from "../types";
import { evaluationPercent } from "../agentEvaluation";

function metric(value: number | null | undefined, digits: number, suffix = "") {
  return value == null ? "N/A" : `${value.toFixed(digits)}${suffix}`;
}

export function AnalysisReportCard({ report }: { report: AnalysisReport }) {
  const best = report.bestCandidate;
  const evaluationMetrics = [
    ["Intent Accuracy", evaluationPercent(report.evaluationReport?.intent_accuracy)],
    ["Parameter Accuracy", evaluationPercent(report.evaluationReport?.parameter_accuracy)],
    ["Tool Calling Success", evaluationPercent(report.evaluationReport?.tool_calling_success)],
    ["Task Success Rate", evaluationPercent(report.evaluationReport?.task_success_rate)],
  ] as const;
  const hasEvaluationData = evaluationMetrics.some(([, value]) => value !== null);

  return (
    <section className="analysis-report" aria-labelledby="analysis-report-title">
      <div className="analysis-report__heading">
        <div><p className="eyebrow">Result intelligence</p><h3 id="analysis-report-title">AI Analysis Report</h3></div>
        <span>Completed analysis</span>
      </div>
      <div className="analysis-report__facts">
        <div><span>Target</span><strong>{report.target}</strong></div>
        <div><span>Generated</span><strong>{report.generated}</strong></div>
        <div><span>Valid Candidates</span><strong>{report.validCandidates}</strong></div>
      </div>
      <div className="analysis-report__candidate">
        <div className="analysis-report__best"><span>Best Candidate</span><code>{best.smiles}</code></div>
        <dl>
          <div><dt>Vina</dt><dd>{metric(best.vina, 2, " kcal/mol")}</dd></div>
          <div><dt>QED</dt><dd>{metric(best.qed, 3)}</dd></div>
          <div><dt>SA</dt><dd>{metric(best.sa, 3)}</dd></div>
          <div><dt>Lipinski</dt><dd>{best.lipinski == null ? "N/A" : best.lipinski ? "PASS" : "FAIL"}</dd></div>
          <div><dt>MolWt</dt><dd>{metric(best.molwt, 1)}</dd></div>
          <div><dt>LogP</dt><dd>{metric(best.logp, 2)}</dd></div>
        </dl>
      </div>
      <div className="analysis-report__evaluation">
        <div className="analysis-report__evaluation-heading">
          <div><span>Agent reliability</span><h4>Agent Evaluation</h4></div>
          {!hasEvaluationData && <small>Awaiting evaluation data</small>}
        </div>
        <div className="evaluation-metrics">
          {evaluationMetrics.map(([label, value]) => (
            <div className={`evaluation-metric ${value === null ? "unavailable" : ""}`} key={label}>
              <div><span>{label}</span><strong>{value === null ? "N/A" : `${value}%`}</strong></div>
              <div className="evaluation-progress" {...(value === null ? { "aria-label": `${label}: N/A` } : { role: "progressbar", "aria-label": label, "aria-valuemin": 0, "aria-valuemax": 100, "aria-valuenow": value })}>
                {value !== null && <i style={{ width: `${value}%` }} />}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
