import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../api";
import { getFigure, renderFigure, type FigureStatus } from "../bindingFigureApi";
import { ApiError } from "../httpClient";
import { MoleculeViewer3D } from "./MoleculeViewer3D";

export function BindingFigure({ taskId, candidateIndex, molBlock, proteinPdb }: {
  taskId?: string; candidateIndex?: number; molBlock?: string | null; proteinPdb?: string | null;
}) {
  const [palette, setPalette] = useState(1);
  const [status, setStatus] = useState<FigureStatus | null>(null);
  const [phase, setPhase] = useState<"idle" | "loading" | "ready" | "rendering" | "unavailable" | "failed">("idle");
  const [message, setMessage] = useState("");
  const [imageFailed, setImageFailed] = useState(false);
  const busy = useRef(false);
  const path = taskId && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(taskId) && Number.isInteger(candidateIndex) && candidateIndex! >= 0
    ? `/api/tasks/${encodeURIComponent(taskId)}/binding-figures/${candidateIndex}` : null;
  const knownReadyKey = path ? `drug-design-agent:binding-ready:${path}` : null;

  useEffect(() => {
    setStatus(null); setPhase("idle"); setMessage(""); setImageFailed(false); busy.current = false;
  }, [taskId, candidateIndex]);

  useEffect(() => {
    if (!path || !knownReadyKey || localStorage.getItem(knownReadyKey) !== "1") return;
    let cancelled = false;
    setPhase("loading");
    void getFigure(API_BASE_URL, path).then(next => {
      if (cancelled) return;
      setStatus(next);
      if (next.palette_id != null) setPalette(next.palette_id);
      setPhase(next.state === "queued" || next.state === "pending" || next.state === "rendering" ? "rendering" : next.state);
      setMessage(next.message ?? "");
    }).catch(error => { if (!cancelled) { setPhase("failed"); setMessage(error instanceof Error ? error.message : "恢复结合图失败"); } });
    return () => { cancelled = true; };
  }, [path, knownReadyKey]);

  useEffect(() => {
    if (status?.state === "ready" && knownReadyKey) localStorage.setItem(knownReadyKey, "1");
  }, [status, knownReadyKey]);

  useEffect(() => {
    if (!path || phase !== "rendering") return;
    let cancelled = false;
    const started = Date.now();
    const timer = window.setInterval(async () => {
      if (busy.current || cancelled) return;
      if (Date.now() - started > 150_000) { setPhase("failed"); setMessage("结合图等待超时，可稍后查询已有图。" ); return; }
      busy.current = true;
      try {
        const next = await getFigure(API_BASE_URL, path);
        if (cancelled) return;
        setStatus(next);
        if (next.palette_id != null) setPalette(next.palette_id);
        if (next.state === "ready") setPhase("ready");
        else if (next.state === "failed" || next.state === "unavailable") { setPhase(next.state); setMessage(next.message ?? "结合图不可用"); }
      } catch (error) { if (!cancelled) { setPhase("failed"); setMessage(error instanceof Error ? error.message : "查询结合图失败"); } }
      finally { busy.current = false; }
    }, 2000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [path, phase]);

  async function loadExisting(locked = false) {
    if (!path || busy.current) return;
    busy.current = true; setPhase("loading"); setMessage("");
    try {
      const next = await getFigure(API_BASE_URL, path);
      setStatus(next);
      if (next.palette_id != null) setPalette(next.palette_id);
      setPhase(next.state === "queued" || next.state === "pending" || next.state === "rendering" ? "rendering" : next.state);
      setMessage(locked ? "该候选已固定配色；已加载现有结果。" : next.message ?? "");
    } catch (error) { setPhase("failed"); setMessage(error instanceof Error ? error.message : "查询结合图失败"); }
    finally { busy.current = false; }
  }

  async function render() {
    if (!path || busy.current || phase === "rendering" || phase === "ready") return;
    busy.current = true; setPhase("loading"); setMessage("");
    try {
      const next = await renderFigure(API_BASE_URL, path, palette);
      setStatus(next);
      if (next.palette_id != null) setPalette(next.palette_id);
      setPhase(next.state === "queued" || next.state === "pending" || next.state === "rendering" ? "rendering" : next.state);
      setMessage(next.message ?? "");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setMessage("该候选已固定配色；正在读取现有结果。" );
        busy.current = false;
        await loadExisting(true);
        return;
      }
      setPhase("failed"); setMessage(error instanceof Error ? error.message : "结合图生成请求失败");
    } finally { busy.current = false; }
  }

  const imageUrl = status?.image_url && API_BASE_URL
    ? new URL(status.image_url, `${API_BASE_URL}/`).href : null;
  return <div className="binding-figure">
    <div className="binding-figure__controls">
      <label>Fig.5 配色 <select value={palette} disabled={status?.palette_id != null || phase === "loading" || phase === "rendering"} onChange={event => setPalette(Number(event.target.value))}>
        {Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>配色 {index + 1}</option>)}
      </select></label>
      {status?.palette_id != null && <span>已固定配色 {status.palette_id}</span>}
      <button type="button" disabled={!path || phase === "loading" || phase === "rendering" || phase === "ready"} onClick={render}>生成结合图</button>
      <button type="button" disabled={!path || phase === "loading"} onClick={() => loadExisting()}>查看已有图</button>
    </div>
    {phase === "idle" && <p>选择配色后可生成；若此前已生成，请点击“查看已有图”。查询状态可能锁定配色。</p>}
    {phase === "ready" && message && <p role="status">{message}</p>}
    {(phase === "loading" || phase === "rendering") && <p role="status">{phase === "loading" ? "正在查询结合图…" : "正在渲染真实结合图…"}</p>}
    {phase === "ready" && imageUrl && !imageFailed && <img className="binding-figure__image" src={imageUrl} alt={`真实蛋白质–配体结合图，配色 ${status?.palette_id ?? palette}`} onError={() => { setImageFailed(true); setMessage("图片加载失败，已切换至三维结构查看。"); }} />}
    {(phase === "failed" || phase === "unavailable" || imageFailed || (phase === "ready" && !imageUrl)) && <>
      <p role="status">{message || "真实结合图不可用，显示原有三维结构。"}</p>
      {molBlock ? <MoleculeViewer3D molBlock={molBlock} proteinPdb={proteinPdb} label="蛋白–配体三维结构共显（非认证对接位姿）" /> : <p>3D 结构暂不可用</p>}
    </>}
  </div>;
}
