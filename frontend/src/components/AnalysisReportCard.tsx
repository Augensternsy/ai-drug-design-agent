import type { AnalysisReport } from "../types";

function metric(value: number | null | undefined, digits: number, suffix = "") {
  return value == null ? "N/A" : `${value.toFixed(digits)}${suffix}`;
}

export function AnalysisReportCard({ report }: { report: AnalysisReport }) {
  const best = report.bestCandidate;

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
    </section>
  );
}
