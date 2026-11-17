import { useState } from "react";
import type { Candidate } from "../types";
import { downloadCandidateSdf } from "../utils/exports";
import { MoleculeViewer3D } from "./MoleculeViewer3D";
import { BindingFigure } from "./BindingFigure";

function metric(value: number | null, digits = 3) {
  return value === null ? "N/A" : value.toFixed(digits);
}

export function MoleculeCard({ candidate, proteinPdb, taskId }: { candidate: Candidate; proteinPdb?: string | null; taskId?: string }) {
  const [viewMode, setViewMode] = useState<"2d" | "3d" | "complex">("2d");
  const [manualPalette, setManualPalette] = useState(false);
  const [palette, setPalette] = useState(1);
  const [openedBinding, setOpenedBinding] = useState(false);
  const [copied, setCopied] = useState(false);
  const [zoom, setZoom] = useState(1);
  const moleculeSvg = candidate.valid ? candidate.molecule_svg ?? candidate.structure_svg : null;
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
        <div><span className="rank">Rank #{candidate.rank}</span><strong>候选分子</strong></div>
        <span className={`pill ${candidate.lipinski === null ? "neutral" : candidate.lipinski ? "pass" : "fail"}`}>{candidate.lipinski === null ? "Lipinski N/A" : candidate.lipinski ? "Lipinski PASS" : "Lipinski FAIL"}</span>
      </header>

      <div className="molecule-view-tabs" role="group" aria-label={`候选分子 ${candidate.rank} 视图`}>
        <button type="button" className={viewMode === "2d" ? "active" : ""} onClick={() => setViewMode("2d")}>查看 2D</button>
        <button type="button" className={viewMode === "3d" ? "active" : ""} onClick={() => setViewMode("3d")}>查看 3D</button>
        <button type="button" className={viewMode === "complex" ? "active" : ""} onClick={() => { setOpenedBinding(true); setViewMode("complex"); }}>结合模式</button>
        {!openedBinding && <details className="binding-figure__advanced"><summary>高级设置 / 手动配色</summary><label><input type="checkbox" checked={manualPalette} onChange={event => setManualPalette(event.target.checked)} />手动选择 Fig.5 配色</label>{manualPalette && <select aria-label="Fig.5 配色" value={palette} onChange={event => setPalette(Number(event.target.value))}>{Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>配色 {index + 1}</option>)}</select>}</details>}
      </div>
      <div className={`molecule-canvas${viewMode === "complex" ? " complex" : ""}`}>
        {!candidate.valid && <p role="alert">RDKit Invalid / 未确认有效：不渲染该候选结构</p>}
        {candidate.valid && viewMode === "2d" && (svgUrl ? <>
          <div className="molecule-2d-viewport"><img src={svgUrl} alt={`候选分子 ${candidate.rank} 的二维结构`} style={{ transform: `scale(${zoom})` }} /></div>
          <div className="molecule-zoom-controls" role="group" aria-label="二维结构缩放">
            <button type="button" aria-label="缩小二维结构" onClick={() => setZoom((value) => Math.max(0.75, value - 0.25))} disabled={zoom <= 0.75}>−</button>
            <button type="button" aria-label="重置二维结构缩放" onClick={() => setZoom(1)}>{Math.round(zoom * 100)}%</button>
            <button type="button" aria-label="放大二维结构" onClick={() => setZoom((value) => Math.min(2.5, value + 0.25))} disabled={zoom >= 2.5}>+</button>
          </div>
        </> : <p>二维结构生成中</p>)}
        {candidate.valid && viewMode === "3d" && (candidate.mol_block || candidate.sdf
          ? <MoleculeViewer3D molBlock={candidate.mol_block || candidate.sdf!} label={`候选分子 ${candidate.rank} 的三维构象`} />
          : <p>3D 结构暂不可用</p>)}
        {candidate.valid && openedBinding && <div hidden={viewMode !== "complex"} className="binding-figure-host"><BindingFigure taskId={taskId} candidateIndex={candidate.candidate_index} requestedPalette={manualPalette ? palette : undefined} molBlock={candidate.mol_block || candidate.sdf} proteinPdb={proteinPdb} /></div>}
      </div>

      {viewMode === "complex" && <p>真实 PNG 来源于后端归档的认证对接位姿；回退三维结构仅为构象共显。</p>}
      <dl className="metric-grid">
        <div><dt>QED</dt><dd>{metric(candidate.qed)}</dd></div>
        <div><dt>SA</dt><dd>{metric(candidate.sa)}</dd></div>
        <div><dt>MolWt</dt><dd>{metric(candidate.molwt, 1)}</dd></div>
        <div><dt>LogP</dt><dd>{metric(candidate.logp, 2)}</dd></div>
        <div><dt>Vina</dt><dd className={candidate.vina == null ? "vina-score unavailable" : "vina-score"}>{candidate.vina == null ? "Not evaluated" : `${candidate.vina.toFixed(2)} kcal/mol`}</dd></div>
      </dl>

      <div className="smiles-block"><span>SMILES</span><code>{candidate.smiles}</code></div>
      <div className="card-actions">
        <button type="button" onClick={copySmiles}>{copied ? "已复制" : "Copy SMILES"}</button>
        <button type="button" onClick={() => downloadCandidateSdf(candidate)} disabled={!candidate.mol_block} title={candidate.mol_block ? "下载该候选分子的 SDF 文件" : "当前候选没有可用的 3D 结构"}>{candidate.mol_block ? "下载 SDF" : "SDF 不可用"}</button>
      </div>
    </article>
  );
}
