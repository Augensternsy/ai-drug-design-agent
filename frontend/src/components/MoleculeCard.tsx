import { useState } from "react";
import type { Candidate } from "../types";
import { downloadCandidateSdf } from "../utils/exports";
import { MoleculeViewer3D } from "./MoleculeViewer3D";

function metric(value: number | null, digits = 3) {
  return value === null ? "N/A" : value.toFixed(digits);
}

export function MoleculeCard({ candidate }: { candidate: Candidate }) {
  const [view, setView] = useState<"2d" | "3d">("2d");
  const [copied, setCopied] = useState(false);
  const svgUrl = candidate.structure_svg
    ? `data:image/svg+xml;charset=utf-8,${encodeURIComponent(candidate.structure_svg)}`
    : null;

  const copySmiles = async () => {
    await navigator.clipboard.writeText(candidate.smiles);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <article className="molecule-card">
      <header className="molecule-card__header">
        <div><span className="rank">#{candidate.rank}</span><strong>候选分子</strong></div>
        <span className={`pill ${candidate.lipinski === null ? "neutral" : candidate.lipinski ? "pass" : "fail"}`}>{candidate.lipinski === null ? "Lipinski N/A" : candidate.lipinski ? "Lipinski PASS" : "Lipinski FAIL"}</span>
      </header>

      <div className="molecule-view-tabs" role="group" aria-label={`候选分子 ${candidate.rank} 视图`}>
        <button type="button" className={view === "2d" ? "active" : ""} onClick={() => setView("2d")}>查看 2D</button>
        <button type="button" className={view === "3d" ? "active" : ""} onClick={() => setView("3d")} disabled={!candidate.sdf}>查看 3D</button>
      </div>
      <div className="molecule-canvas">
        {view === "2d" && (svgUrl ? <img src={svgUrl} alt={`候选分子 ${candidate.rank} 的二维结构`} /> : <p>二维结构暂不可用</p>)}
        {view === "3d" && candidate.sdf && <MoleculeViewer3D sdf={candidate.sdf} label={`候选分子 ${candidate.rank} 的三维构象`} />}
      </div>

      <dl className="metric-grid">
        <div><dt>QED</dt><dd>{metric(candidate.qed)}</dd></div>
        <div><dt>SA</dt><dd>{metric(candidate.sa)}</dd></div>
        <div><dt>MolWt</dt><dd>{metric(candidate.molwt, 1)}</dd></div>
        <div><dt>LogP</dt><dd>{metric(candidate.logp, 2)}</dd></div>
        <div><dt>Vina</dt><dd className="vina-score">{candidate.vina === null ? "N/A" : `${candidate.vina.toFixed(2)} kcal/mol`}</dd></div>
      </dl>

      <div className="smiles-block"><span>SMILES</span><code>{candidate.smiles}</code></div>
      <div className="card-actions">
        <button type="button" onClick={copySmiles}>{copied ? "已复制" : "Copy SMILES"}</button>
        <button type="button" onClick={() => downloadCandidateSdf(candidate)} disabled={!candidate.sdf}>下载 SDF</button>
      </div>
    </article>
  );
}
