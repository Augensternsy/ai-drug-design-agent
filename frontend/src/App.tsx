import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { normalizeAgentPlan } from "./agentPlan";
import { API_BASE_URL, apiRequest } from "./api";
import { checkBackendHealth, type BackendMode } from "./backend";
import { buildAnalysisReport, rankCandidates } from "./candidateRanking";
import { loadAgentEvaluationReport } from "./agentEvaluation";
import { displayTaskStage } from "./modelDisplay";
import { AnalysisReportCard } from "./components/AnalysisReportCard";
import { DiscoveryPipeline } from "./components/DiscoveryPipeline";
import { MoleculeCard } from "./components/MoleculeCard";
import { TaskLoadingCard } from "./components/TaskLoadingCard";
import { createVerifiedDemoTask, parseDemoPrompt } from "./demo";
import { pollTaskUntilTerminal } from "./taskPolling";
import type { AgentEvaluationReport, AgentGenerateResponse, GenerateResponse, StoredTask, Task } from "./types";
import { downloadAllSdf, exportTaskCsv, exportTaskJson } from "./utils/exports";
import { clearHistory, loadHistory, saveTaskToHistory, loadActiveTask, saveActiveTask, clearActiveTask, validTaskId } from "./utils/history";

const TARGETS = [
  ["ESR1", "2R6W"], ["HCRTR1", "4ZJC"], ["JAK1", "3EYG"], ["P2RX3", "5SVL"],
  ["KDM1A", "5LHG"], ["IDH1", "4UMX"], ["RIOK1", "4OTP"], ["NR4A1", "3V3Q"],
  ["GRIK1", "3FV1"], ["CCR9", "5LWE"], ["FTO", "4ZS3"], ["SPIN1", "5JSJ"],
] as const;

const MAX_SAMPLES = 5;
const COOLDOWN_SECONDS = 15;
const DISPLAY_STAGES = ["queued", "generating", "evaluating", "docking", "completed"] as const;
type DisplayStage = (typeof DISPLAY_STAGES)[number];

const STAGE_LABELS: Record<DisplayStage, string> = {
  queued: "任务排队", generating: "分子生成", evaluating: "性质评估", docking: "Vina 对接", completed: "生成完成",
};

const STATUS_LABELS: Record<string, string> = {
  pending: "任务等待执行",
  queued: "任务已提交", running: "正在生成候选分子", processing: "正在生成候选分子",
  loading: "正在生成候选分子", encoding: "正在生成候选分子", generating: "正在生成候选分子",
  evaluating: "正在生成候选分子", docking: "正在生成候选分子", ranking: "正在生成候选分子",
  completed: "候选分子已生成", failed: "任务执行失败",
};

type PendingSubmission =
  | { kind: "form"; target: string; count: number; qed: number | null; sa: number | null; docking: boolean }
  | { kind: "agent"; prompt: string };

function displayStageFor(status: string): DisplayStage {
  if (["queued", "loading", "encoding"].includes(status)) return "queued";
  if (status === "generating") return "generating";
  if (status === "docking") return "docking";
  if (status === "completed") return "completed";
  return "evaluating";
}

function emptyTask(response: GenerateResponse, target: string, requested: number, agent = false, agentPlan: Task["agent_plan"] = null): Task {
  return {
    task_id: response.task_id, target, status: response.status, progress: null, current_stage: response.message,
    error: null, requested, generated: null, valid: null, returned: null, candidates: [], requested_by_agent: agent,
    agent_plan: agentPlan, tool_trace: [], summary: null,
  };
}

function App() {
  const [mode, setMode] = useState<"form" | "agent">("form");
  const [target, setTarget] = useState("ESR1");
  const [count, setCount] = useState(1);
  const [qedThreshold, setQedThreshold] = useState("");
  const [saThreshold, setSaThreshold] = useState("");
  const [runDocking, setRunDocking] = useState(false);
  const [agentPrompt, setAgentPrompt] = useState("");
  const [task, setTask] = useState<Task | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [queryId, setQueryId] = useState("");
  const [queryRevision, setQueryRevision] = useState(0);
  const [unresolved, setUnresolved] = useState(false);
  const submissionLock = useRef(false);
  const submissionController = useRef<AbortController | null>(null);
  const [submittedWithDocking, setSubmittedWithDocking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [loading, setLoading] = useState(false);
  const [pending, setPending] = useState<PendingSubmission | null>(null);
  const [cooldown, setCooldown] = useState(0);
  const [history, setHistory] = useState<StoredTask[]>(() => loadHistory());
  const [historyOpen, setHistoryOpen] = useState(false);
  const [backendMode, setBackendMode] = useState<BackendMode>("checking");
  const [evaluationReport, setEvaluationReport] = useState<AgentEvaluationReport | null>(null);
  const lastSavedTask = useRef<string | null>(null);

  const running = submitting || loading || unresolved;
  const rankedCandidates = useMemo(() => rankCandidates(task?.candidates ?? []), [task?.candidates]);
  const analysisReport = useMemo(
    () => buildAnalysisReport(task, rankedCandidates, evaluationReport),
    [task, rankedCandidates, evaluationReport],
  );
  const rankedTask = useMemo(() => task ? { ...task, candidates: rankedCandidates } : null, [task, rankedCandidates]);
  const hasDownloadableSdf = rankedCandidates.some((candidate) => Boolean(candidate.mol_block));
  const activeStage = displayStageFor(task?.status ?? "queued");
  const taskState = task?.status === "failed" ? "failed" : task?.status === "completed" ? "complete" : "running";
  const visibleStages = useMemo(
    () => submittedWithDocking ? DISPLAY_STAGES : DISPLAY_STAGES.filter((stage) => stage !== "docking"),
    [submittedWithDocking],
  );

  useEffect(() => {
    let active = true;
    void (async () => {
      const nextMode = await checkBackendHealth(API_BASE_URL);
      if (!active) return;
      setBackendMode(nextMode);
      if (nextMode === "live") {
        const savedId = loadActiveTask(API_BASE_URL);
        if (savedId) { setQueryId(savedId); setTaskId(savedId); setUnresolved(true); }
        const report = await loadAgentEvaluationReport(API_BASE_URL);
        if (active) setEvaluationReport(report);
        return;
      }
      setSubmittedWithDocking(false);
      setTask(createVerifiedDemoTask("ESR1", 1, false));
    })();
    return () => { active = false; };
  }, []);

  useEffect(() => () => { submissionController.current?.abort(); }, []);

  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = window.setInterval(() => setCooldown((value) => Math.max(0, value - 1)), 1000);
    return () => window.clearInterval(timer);
  }, [cooldown > 0]);

  useEffect(() => {
    if (!taskId) return;
    let active = true;
    const controller = new AbortController();
    setLoading(true);
    pollTaskUntilTerminal(taskId, {
      fetchTask: (id, signal, timeout) => apiRequest<unknown>(`/api/tasks/${encodeURIComponent(id)}`, { signal }, timeout),
      initialTask: task?.task_id === taskId ? task : undefined,
      signal: controller.signal,
      onUpdate: (nextTask) => {
        if (!active) return;
        setTask(nextTask);
        setSubmittedWithDocking((previous) => previous || nextTask.agent_plan?.run_docking === true
          || nextTask.tools?.some((tool) => /vina|docking/i.test(tool.name) && tool.status !== "skipped") === true
          || nextTask.candidates.some((candidate) => candidate.vina != null));
        setError(nextTask.error ?? (nextTask.status === "failed" ? "任务执行失败，请检查参数后重试。" : null));
      },
      onTransientError: (pollError) => {
        if (!active) return;
        setError(pollError instanceof Error ? `任务状态更新暂时失败，正在继续轮询：${pollError.message}` : "任务状态更新暂时失败，正在继续轮询。");
      },
    }).then((finalTask) => {
      if (!active) return;
      setTask(finalTask);
      setError(finalTask.error ?? (finalTask.status === "failed" ? "任务执行失败，请检查参数后重试。" : null));
      setLoading(false);
      setUnresolved(false);
      clearActiveTask(API_BASE_URL, taskId);
    }).catch((pollError) => {
      if (!active || (pollError instanceof DOMException && pollError.name === "AbortError")) return;
      setLoading(false);
      if (pollError && typeof pollError === "object" && "status" in pollError && pollError.status === 404) {
        setUnresolved(false);
        clearActiveTask(API_BASE_URL, taskId);
      }
      setError(pollError instanceof Error ? pollError.message : "无法获取任务状态，请稍后重试。");
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [taskId, queryRevision]);

  useEffect(() => {
    if (!task || !["completed", "failed"].includes(task.status) || lastSavedTask.current === task.task_id) return;
    lastSavedTask.current = task.task_id;
    setHistory(saveTaskToHistory(task));
  }, [task]);

  const prepareFormSubmission = (event: FormEvent) => {
    event.preventDefault();
    if (running || cooldown > 0) return;
    setPending({
      kind: "form", target, count,
      qed: qedThreshold ? Number(qedThreshold) : null,
      sa: saThreshold ? Number(saThreshold) : null,
      docking: runDocking,
    });
  };

  const prepareAgentSubmission = (event: FormEvent) => {
    event.preventDefault();
    if (running || cooldown > 0 || agentPrompt.trim().length < 3) return;
    setPending({ kind: "agent", prompt: agentPrompt.trim() });
  };

  const confirmSubmission = async () => {
    if (!pending || running || cooldown > 0 || submissionLock.current) return;
    submissionLock.current = true;
    const controller = new AbortController();
    submissionController.current = controller;
    const submission = pending;
    setPending(null);
    setSubmitting(true);
    setLoading(false);
    setError(null);
    setTask(null);
    setTaskId(null);

    try {
      if (backendMode === "demo") {
        if (submission.kind === "form") {
          setSubmittedWithDocking(false);
          setTask(createVerifiedDemoTask(submission.target, submission.count, submission.docking));
        } else {
          const parsed = parseDemoPrompt(submission.prompt);
          setSubmittedWithDocking(false);
          setTask(createVerifiedDemoTask(parsed.target, parsed.count, false, true));
        }
        setCooldown(COOLDOWN_SECONDS);
        setLoading(false);
        return;
      }
      if (backendMode !== "live") return;

      if (submission.kind === "form") {
        setSubmittedWithDocking(submission.docking);
        const response = await apiRequest<GenerateResponse>("/api/generate", {
          signal: controller.signal,
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            target: submission.target, num_samples: submission.count,
            qed_threshold: submission.qed, sa_threshold: submission.sa, run_docking: submission.docking,
          }),
        });
        if (!validTaskId(response.task_id ?? "")) throw new Error("创建响应缺少有效任务 ID；请勿重复提交。");
        saveActiveTask(API_BASE_URL, response.task_id);
        setUnresolved(true);
        setQueryId(response.task_id);
        setTaskId(response.task_id);
        setTask(emptyTask(response, submission.target, submission.count));
        setLoading(true);
      } else {
        const response = await apiRequest<AgentGenerateResponse>("/api/agent/generate", {
          signal: controller.signal,
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ prompt: submission.prompt }),
        });
        const agentPlan = normalizeAgentPlan(response.plan);
        setSubmittedWithDocking(agentPlan.run_docking);
        if (!validTaskId(response.task_id ?? "")) throw new Error("创建响应缺少有效任务 ID；请勿重复提交。");
        saveActiveTask(API_BASE_URL, response.task_id);
        setUnresolved(true);
        setQueryId(response.task_id);
        setTaskId(response.task_id);
        setTask(emptyTask(response, agentPlan.target, agentPlan.num_samples, true, agentPlan));
        setLoading(true);
      }
      setCooldown(COOLDOWN_SECONDS);
    } catch (submitError) {
      if (!(submitError && typeof submitError === "object" && "status" in submitError)) setUnresolved(true);
      setLoading(false);
      setError(submitError instanceof Error ? submitError.message : "任务提交失败，请稍后重试。");
    } finally {
      submissionLock.current = false;
      setSubmitting(false);
    }
  };

  const restoreHistory = (item: StoredTask) => {
    setTaskId(null);
    setLoading(false);
    setTask(item.task);
    setSubmittedWithDocking(item.task.agent_plan?.run_docking ?? item.task.candidates.some((candidate) => candidate.vina != null));
    setError(item.task.error);
    setHistoryOpen(false);
  };

  const backendLabel = backendMode === "live"
    ? "API 已连接 · GPU 按需加载"
    : backendMode === "demo"
      ? "Demo Mode"
      : "Checking GPU…";

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="AI Drug Design Agent 首页">
          <span className="brand-mark" aria-hidden="true">AI</span>
          <span><strong>Drug Design Agent</strong><small>GPU molecular discovery workspace</small></span>
        </a>
        <div className="header-actions">
          <button type="button" className="history-trigger" onClick={() => setHistoryOpen((value) => !value)} aria-expanded={historyOpen}>历史任务 <span>{history.length}</span></button>
          <div className={`system-badge ${backendMode}`} role="status"><span />{backendLabel}</div>
        </div>
      </header>

      {backendMode === "demo" && <div className="backend-notice demo"><strong>Demo / Precomputed Result</strong><span>后端健康检查未通过；仅展示预置 SMILES，不为当前所选靶点实时生成，也不会请求 Vina。</span></div>}

      {historyOpen && (
        <aside className="history-panel" aria-label="最近任务">
          <div className="history-panel__header"><strong>最近任务</strong><button type="button" onClick={() => { clearHistory(); setHistory([]); }}>清空</button></div>
          {history.length ? history.map((item) => (
            <button type="button" className="history-item" key={item.task.task_id} onClick={() => restoreHistory(item)}>
              <span><strong>{item.task.target}</strong><small>{new Date(item.savedAt).toLocaleString()}</small></span>
              <span>{item.task.returned ?? item.task.candidates.length} molecules · {item.task.status}</span>
            </button>
          )) : <p>暂无本地历史。完成的任务会保存在当前浏览器中。</p>}
        </aside>
      )}

      <main id="top">
        <section className="hero">
          <div>
            <p className="eyebrow">Target-guided molecular generation</p>
            <h1>从蛋白靶点出发，<br /><span>生成并筛选候选分子。</span></h1>
            <p className="hero-copy">Agent 负责任务解析与工具编排；ESM-2、部署模型 AP-MolDiff、RDKit 与可选 AutoDock Vina 完成专业计算。DLPS-E2PO 是模型的偏好优化方法；论文实验范围为 12 个测试靶点。</p>
          </div>
          <div className="pipeline" aria-label="推理流程">
            {["ESM-2 · Protein encoding", "AP-MolDiff · Molecule generation", "RDKit + Vina · Evaluate & optional dock"].map((item, index) => {
              const [title, subtitle] = item.split(" · ");
              return <div className="pipeline-item" key={item}><span>0{index + 1}</span><strong>{title}</strong><small>{subtitle}</small></div>;
            })}
          </div>
        </section>

        <section className="agent-workspace">
          <form className="task-query" onSubmit={(event) => {
            event.preventDefault();
            const id = queryId.trim();
            if (!validTaskId(id)) { setError("请输入有效 Task ID。"); return; }
            setError(null); setTask(null); setSubmittedWithDocking(false); setUnresolved(true);
            saveActiveTask(API_BASE_URL, id); setTaskId(id); setQueryRevision(value => value + 1);
          }}>
            <label htmlFor="task-query-id">查询已有 Task ID（只读）</label>
            <input id="task-query-id" value={queryId} onChange={event => setQueryId(event.target.value)} maxLength={100} />
            <button disabled={backendMode !== "live" || loading || submitting || !queryId.trim()}>查询 / 继续查询</button>
            {unresolved && !loading && <span>状态尚未确认；不会自动重新创建任务。</span>}
            {unresolved && <button type="button" onClick={() => {
              if (!window.confirm("仅停止本页跟踪，不取消后端任务。请保存 Task ID，避免重复创建。确认停止？")) return;
              if (taskId) clearActiveTask(API_BASE_URL, taskId);
              setTaskId(null); setLoading(false); setUnresolved(false);
            }}>停止本页跟踪</button>}
          </form>
          <div className="mode-tabs" role="tablist" aria-label="任务输入方式">
            <button type="button" role="tab" aria-selected={mode === "form"} className={mode === "form" ? "active" : ""} onClick={() => setMode("form")}>参数表单</button>
            <button type="button" role="tab" aria-selected={mode === "agent"} className={mode === "agent" ? "active" : ""} onClick={() => setMode("agent")}>自然语言 Agent</button>
          </div>

          {mode === "agent" && (
            <form className="agent-prompt" onSubmit={prepareAgentSubmission}>
              <label htmlFor="agent-prompt"><span>Agent 指令</span><small>后端 LLM 不可用时可回退至规则解析；实际解析方式以任务结果为准</small></label>
              <textarea id="agent-prompt" rows={4} maxLength={500} value={agentPrompt} onChange={(event) => setAgentPrompt(event.target.value)} disabled={running} placeholder="例如：帮我针对 ESR1 生成 5 个候选分子，QED 优先，SA&lt;3.5，并对最优结果进行 Vina 对接。" />
              <div className="agent-prompt__footer"><span>{agentPrompt.length}/500</span><button type="submit" disabled={running || cooldown > 0 || backendMode === "checking" || agentPrompt.trim().length < 3}>{cooldown > 0 ? `${cooldown}s 后可提交` : backendMode === "checking" ? "检查后端中…" : "交给 Agent →"}</button></div>
            </form>
          )}
        </section>

        <section className={`workspace-grid ${mode === "agent" ? "agent-mode" : ""}`}>
          <form className="control-panel" onSubmit={prepareFormSubmission} hidden={mode !== "form"}>
            <div className="section-heading"><div><span>01</span><h2>生成设置</h2></div><p>公开 Demo 单次最多 5 个候选。</p></div>
            <label className="field-label" htmlFor="target">蛋白靶点</label>
            <div className="select-wrap"><select id="target" value={target} onChange={(event) => setTarget(event.target.value)} disabled={running}>{TARGETS.map(([name, pdb]) => <option value={name} key={name}>{name} · PDB {pdb}</option>)}</select></div>
            <p className="field-hint">预置论文实验的 12 个测试靶点；当前已完成的正式生产验收案例为 ESR1。</p>

            <label className="field-label" htmlFor="count">生成数量</label>
            <div className="number-control">
              <button type="button" onClick={() => setCount((value) => Math.max(1, value - 1))} disabled={running || count <= 1} aria-label="减少生成数量">−</button>
              <input id="count" type="number" min="1" max={MAX_SAMPLES} value={count} onChange={(event) => setCount(Math.min(MAX_SAMPLES, Math.max(1, Number(event.target.value) || 1)))} disabled={running} />
              <button type="button" onClick={() => setCount((value) => Math.min(MAX_SAMPLES, value + 1))} disabled={running || count >= MAX_SAMPLES} aria-label="增加生成数量">+</button>
            </div>

            <div className="threshold-grid">
              <label><span>QED 最低值</span><input type="number" min="0" max="1" step="0.05" value={qedThreshold} onChange={(event) => setQedThreshold(event.target.value)} placeholder="可选" disabled={running} /></label>
              <label><span>SA 最高值</span><input type="number" min="1" max="10" step="0.1" value={saThreshold} onChange={(event) => setSaThreshold(event.target.value)} placeholder="可选" disabled={running} /></label>
            </div>

            <label className="toggle-row" htmlFor="run-docking"><span><strong>AutoDock Vina</strong><small>默认关闭；启用会增加 GPU 占用与任务耗时</small></span><input id="run-docking" type="checkbox" checked={runDocking} onChange={(event) => setRunDocking(event.target.checked)} disabled={running} /><i aria-hidden="true" /></label>
            <button className="submit-button" type="submit" disabled={running || cooldown > 0 || backendMode === "checking"}>{running ? <><span className="spinner" />任务执行中</> : cooldown > 0 ? <>冷却中 <span>{cooldown}s</span></> : backendMode === "checking" ? <>检查后端中 <span className="spinner" /></> : backendMode === "demo" ? <>查看预计算结果 <span>→</span></> : <>检查并生成 <span>→</span></>}</button>
            <p className="submit-hint">提交前会再次确认；任务开始后按钮将锁定。</p>
            {backendMode === "demo" && <p className="config-warning">Demo Mode 不会请求后端；所有结果均明确标注为预计算内容。</p>}
          </form>

          <section className="status-panel" aria-live="polite" aria-busy={running}>
            <div className="section-heading"><div><span>02</span><h2>任务进度</h2></div>{task && <code>{task.task_id.slice(0, 8)}</code>}</div>
            {!task ? <div className="empty-state"><div className="molecule-orbit"><i /><i /><i /></div><strong>等待生成任务</strong><p>{mode === "agent" ? "输入自然语言需求，Agent 将展示工具执行状态。" : "提交后可在这里查看生成、评价与对接进度。"}</p></div> : (
              <div className="task-state">
                <div className={`live-status ${taskState}`} role="status"><span className="live-status-dot" /><div><strong>{task.data_origin === "precomputed_demo" ? "预计算结果已载入" : STATUS_LABELS[task.status] ?? task.status}</strong><small>{task.target} · {task.data_origin === "precomputed_demo" ? "DEMO / PRECOMPUTED" : task.parser_mode ? `AGENT ${task.parser_mode.toUpperCase()}` : task.requested_by_agent ? `AGENT ${task.agent_plan?.parser ?? "RULES"}` : "FORM"}</small></div></div>
                {(task.current_stage || task.progress !== null) && <div className="progress-meta">{task.current_stage && <span>{displayTaskStage(task.current_stage)}</span>}{task.progress !== null && <strong>{Math.round(task.progress)}%</strong>}</div>}
                {task.progress !== null && <div className="progress-track" role="progressbar" aria-label="任务完成进度" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(task.progress)}><div style={{ width: `${task.progress}%` }} /></div>}
                {task.data_origin !== "precomputed_demo" && <ol className="stage-list">{visibleStages.map((stage) => { const index = DISPLAY_STAGES.indexOf(stage); const active = stage === activeStage && task.status !== "failed"; return <li className={active ? "active" : ""} key={stage}><span>{index + 1}</span><div><strong>{STAGE_LABELS[stage]}</strong><small>{stage}</small></div></li>; })}</ol>}
                <DiscoveryPipeline tools={task.tools?.length ? task.tools : task.tool_trace} />
                {task.result_status === "partial" && <p role="alert">部分结果：任务未全部成功，仅展示已保存的候选。</p>}
                <p>数据来源：{task.data_origin === "synthetic_test" ? "Synthetic test / 合成测试，非生产结果" : task.data_origin === "live_runtime" ? "Live runtime" : task.task_id.startsWith("demo-") ? "Demo / Precomputed Result" : "来源未标注"}</p>
                {task.agent_plan && <p>{task.data_origin === "precomputed_demo" ? "Demo 参数预览" : "Agent Plan"}：{task.agent_plan.target} · 数量 {task.agent_plan.num_samples} · QED ≥ {task.agent_plan.qed_threshold ?? "N/A"} · SA ≤ {task.agent_plan.sa_threshold ?? "N/A"} · Vina {task.agent_plan.run_docking ? "开启" : "关闭"}</p>}
                {[task.generated, task.valid, task.returned].some((value) => value !== null) && <div className="task-counts">{task.generated !== null && <span>生成 <strong>{task.generated}</strong></span>}{task.valid !== null && <span>有效 <strong>{task.valid}</strong></span>}{task.returned !== null && <span>返回 <strong>{task.returned}</strong></span>}</div>}
                {task.summary && <p className="result-summary">{task.summary}</p>}
              </div>
            )}
            {error && <div className="error-message" role="alert"><strong>任务异常</strong><span>{error}</span><small>任务状态错误不会切换到 Demo Mode；生成或 Vina 失败会保留真实错误。</small></div>}
          </section>
        </section>

        <section className="results-section">
          <div className="results-header"><div><p className="eyebrow">Ranked candidates</p><h2>候选分子</h2></div><div className="result-actions"><span>{rankedCandidates.length} molecules</span>{rankedTask && rankedCandidates.length ? <><button type="button" onClick={() => exportTaskCsv(rankedTask)}>导出 CSV</button><button type="button" onClick={() => exportTaskJson(rankedTask)}>导出 JSON</button><button type="button" onClick={() => downloadAllSdf(rankedTask)} disabled={!hasDownloadableSdf} title={hasDownloadableSdf ? "合并下载所有可用的 SDF 结构" : "当前结果没有可下载的 3D 结构"}>下载全部 SDF</button></> : null}</div></div>
          {analysisReport && <AnalysisReportCard report={analysisReport} />}
          {rankedCandidates.length ? <div className="molecule-grid">{rankedCandidates.map((candidate) => <MoleculeCard candidate={candidate} proteinPdb={task?.protein_pdb} key={`${candidate.rank}-${candidate.smiles}`} />)}</div> : loading && task ? <TaskLoadingCard task={task} /> : <div className="results-empty"><span>∿</span><p>{task?.status === "completed" ? "任务已结束，没有返回候选分子。" : task?.status === "failed" ? "任务失败，没有可展示的候选。" : "任务完成后，候选分子将在这里以 2D/3D 卡片展示。"}</p></div>}
        </section>
      </main>

      {pending && <div className="dialog-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPending(null); }}><section className="confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="confirm-title"><p className="eyebrow">{backendMode === "demo" ? "Demo disclosure" : "GPU cost check"}</p><h2 id="confirm-title">{backendMode === "demo" ? "确认查看预计算结果？" : "确认提交生成任务？"}</h2><p>{pending.kind === "form" ? `${pending.target} · ${pending.count} 个候选 · Vina ${pending.docking ? "开启" : "关闭"}` : pending.prompt}</p><ul>{backendMode === "demo" ? <><li>当前为 Demo Mode，不会请求 RTX 3090 后端。</li><li>预置 SMILES 不代表为本次所选靶点实时生成；缺失指标显示 N/A。</li><li>本次不会执行 RDKit、分子生成或 Vina。</li></> : <><li>提交后页面会持续显示任务进度，请保持页面开启。</li><li>单次最多 5 个候选，提交后进入 15 秒冷却。</li><li>Vina 会增加执行时间；仅在确有需要时开启。</li></>}</ul><div><button type="button" className="secondary-button" onClick={() => setPending(null)}>返回修改</button><button type="button" className="primary-button" onClick={confirmSubmission}>确认</button></div></section></div>}

      <footer><span>智能药物设计 Agent 系统</span><span>Agent → ESM-2 → AP-MolDiff → RDKit → 可选 AutoDock Vina</span></footer>
    </div>
  );
}

export default App;
