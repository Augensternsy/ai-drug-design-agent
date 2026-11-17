import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "../api";
import { getFigure, hasVerifiedPoseReadyForRendering, isMissingVerifiedVinaPose, renderFigure, type FigureStatus } from "../bindingFigureApi";
import { ApiError } from "../httpClient";
import { MoleculeViewer3D } from "./MoleculeViewer3D";

export function BindingFigure({ taskId, candidateIndex, requestedPalette, molBlock, proteinPdb }: {
  taskId?: string; candidateIndex?: number; requestedPalette?: number; molBlock?: string | null; proteinPdb?: string | null;
}) {
  const [status, setStatus] = useState<FigureStatus | null>(null);
  const [phase, setPhase] = useState<"idle" | "loading" | "ready" | "rendering" | "unavailable" | "failed">("idle");
  const [message, setMessage] = useState("");
  const [imageFailed, setImageFailed] = useState(false);
  const busy = useRef(false);
  const path = taskId && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(taskId) && Number.isInteger(candidateIndex) && candidateIndex! >= 0
    ? `/api/tasks/${encodeURIComponent(taskId)}/binding-figures/${candidateIndex}` : null;
  const knownReadyKey = path ? `drug-design-agent:binding-ready:${path}` : null;
  const submittedKey = path ? `drug-design-agent:binding-submitted:${path}` : null;

  useEffect(() => {
    setStatus(null); setPhase("idle"); setMessage(""); setImageFailed(false); busy.current = false;
  }, [taskId, candidateIndex]);

  useEffect(() => {
    if (!path || !submittedKey) return;
    let cancelled = false;
    setPhase("loading");
    void (async () => {
      try {
        const previouslySubmitted = sessionStorage.getItem(submittedKey) === "1";
        const initial = requestedPalette !== undefined && !previouslySubmitted
          ? await submit(requestedPalette) : await getFigure(API_BASE_URL, path);
        if (cancelled) return;
        let next = initial;
        if (requestedPalette === undefined && !previouslySubmitted && hasVerifiedPoseReadyForRendering(initial)) next = await submit();
        if (cancelled) return;
        setStatus(next); setPhase(toPhase(next)); setMessage(next.message ?? "");
      } catch (error) {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 409) {
          try { const next = await getFigure(API_BASE_URL, path); if (!cancelled) { setStatus(next); setPhase(toPhase(next)); setMessage("该候选配色已锁定；已读取原有结果。"); } } catch (lookupError) { if (!cancelled) { setPhase("failed"); setMessage(String(lookupError)); } }
        } else { setPhase("failed"); setMessage(error instanceof Error ? error.message : "结合图请求失败"); }
      }
    })();
    return () => { cancelled = true; };
  }, [path, submittedKey, requestedPalette]);

  function toPhase(next: FigureStatus) { return next.state === "queued" || next.state === "pending" || next.state === "rendering" ? "rendering" : next.state; }
  async function submit(paletteId?: number) {
    if (!path || !submittedKey) throw new Error("无效的任务");
    if (sessionStorage.getItem(submittedKey) === "1") return getFigure(API_BASE_URL, path);
    sessionStorage.setItem(submittedKey, "1");
    return renderFigure(API_BASE_URL, path, paletteId);
  }

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
        if (next.state === "ready") setPhase("ready");
        else if (next.state === "failed" || next.state === "unavailable") { setPhase(next.state); setMessage(next.message ?? "结合图不可用"); }
      } catch (error) { if (!cancelled) { setPhase("failed"); setMessage(error instanceof Error ? error.message : "查询结合图失败"); } }
      finally { busy.current = false; }
    }, 2000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [path, phase]);

  const imageUrl = status?.image_url && API_BASE_URL
    ? new URL(status.image_url, `${API_BASE_URL}/`).href : null;
  const missingPose = isMissingVerifiedVinaPose(status);
  return <div className="binding-figure">
    <div className="binding-figure__controls">
      {status?.palette_id != null && phase !== "unavailable" && !missingPose && <span>已固定配色 {status.palette_id}</span>}
    </div>
    {phase === "idle" && <p>准备查询真实结合图…</p>}
    {phase === "ready" && message && <p role="status">{message}</p>}
    {(phase === "loading" || phase === "rendering") && <p role="status">正在生成真实结合图…</p>}
    {phase === "ready" && imageUrl && !imageFailed && <img className="binding-figure__image" src={imageUrl} alt={`真实蛋白质–配体结合图，配色 ${status?.palette_id ?? "未知"}`} onError={() => { setImageFailed(true); setMessage("图片加载失败，已切换至三维结构查看。"); }} />}
    {(phase === "failed" || phase === "unavailable" || imageFailed || (phase === "ready" && !imageUrl)) && <>
      <p role="status">{missingPose ? "当前任务未保存真实对接位姿，无法生成蛋白质–配体结合图。Vina评分仍可正常查看。" : message || "真实结合图不可用，显示原有三维结构。"}</p>
      {molBlock ? <MoleculeViewer3D molBlock={molBlock} proteinPdb={proteinPdb} label="蛋白–配体三维结构共显（非认证对接位姿）" /> : <p>3D 结构暂不可用</p>}
    </>}
  </div>;
}
