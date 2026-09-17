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
  const [zoom, setZoom] = useState(1);
  const moleculeSvg = candidate.molecule_svg ?? candidate.structure_svg;
  const svgUrl = moleculeSvg
    ? moleculeSvg.startsWith("data:image/svg+xml")
      ? moleculeSvg
      : `data:image/svg+xml;charset=utf-8,${encodeURIComponent(moleculeSvg)}`
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
        {view === "2d" && (svgUrl ? <>
          <div className="molecule-2d-viewport"><img src={svgUrl} alt={`候选分子 ${candidate.rank} 的二维结构`} style={{ transform: `scale(${zoom})` }} /></div>
          <div className="molecule-zoom-controls" role="group" aria-label="二维结构缩放">
            <button type="button" aria-label="缩小二维结构" onClick={() => setZoom((value) => Math.max(0.75, value - 0.25))} disabled={zoom <= 0.75}>−</button>
            <button type="button" aria-label="重置二维结构缩放" onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button>
            <button type="button" aria-label="放大二维结构" onClick={() => setZoom((value) => Math.min(2.5, value + 0.25))} disabled={zoom >= 2.5}>+</button>
          </div>
        </> : <p>二维结构生成中</p>)}
        {view === "3d" && candidate.sdf && <MoleculeViewer3D sdf={candidate.sdf} label={`候选分子 ${candidate.rank} 的三维构象`} />}
      </div>

      <dl className="metric-grid">
        <div><dt>QED</dt><dd>{metric(candidate.qed)}</dd></div>
        <div><dt>SA</dt><dd>{metric(candidate.sa)}</dd></div>
        <div><dt>MolWt</dt><dd>{metric(candidate.molwt, 1)}</dd></div>
        <div><dt>LogP</dt><dd>{metric(candidate.logp, 2)}</dd></div>
        {candidate.vina !== null && <div><dt>Vina</dt><dd className="vina-score">{candidate.vina.toFixed(2)} kcal/mol</dd></div>}
      </dl>

      <div className="smiles-block"><span>SMILES</span><code>{candidate.smiles}</code></div>
      <div className="card-actions">
        <button type="button" onClick={copySmiles}>{copied ? "已复制" : "Copy SMILES"}</button>
        <button type="button" onClick={() => downloadCandidateSdf(candidate)} disabled={!candidate.sdf}>下载 SDF</button>
      </div>
    </article>
  );
}
