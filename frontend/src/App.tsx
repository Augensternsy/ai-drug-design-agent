import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

const TARGETS = [
  ["ESR1", "2R6W"],
  ["HCRTR1", "4ZJC"],
  ["JAK1", "3EYG"],
  ["P2RX3", "5SVL"],
  ["KDM1A", "5LHG"],
  ["IDH1", "4UMX"],
  ["RIOK1", "4OTP"],
  ["NR4A1", "3V3Q"],
  ["GRIK1", "3FV1"],
  ["CCR9", "5LWE"],
  ["FTO", "4ZS3"],
  ["SPIN1", "5JSJ"],
] as const;

const DISPLAY_STAGES = ["queued", "generating", "evaluating", "docking", "completed"] as const;
type DisplayStage = (typeof DISPLAY_STAGES)[number];

const STAGE_LABELS: Record<DisplayStage, string> = {
  queued: "任务排队",
  generating: "分子生成",
  evaluating: "性质评估",
  docking: "Vina 对接",
  completed: "生成完成",
};

type Candidate = {
  rank: number;
  smiles: string;
  valid: boolean;
  qed: number | null;
  sa: number | null;
  molwt: number | null;
  logp: number | null;
  lipinski: boolean | null;
  vina: number | null;
};

type Task = {
  task_id: string;
  target: string;
  status: string;
  progress: number;
  current_stage: string;
  error: string | null;
  requested: number;
  generated: number;
  valid: number;
  returned: number;
  candidates: Candidate[];
};

type GenerateResponse = {
  task_id: string;
  status: string;
  message: string;
};

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

function displayStageFor(status: string, runDocking: boolean): DisplayStage {
  if (["queued", "loading", "encoding"].includes(status)) return "queued";
  if (status === "generating") return "generating";
  if (status === "docking") return "docking";
  if (status === "completed") return "completed";
  if (["evaluating", "ranking"].includes(status)) return "evaluating";
  return runDocking ? "docking" : "evaluating";
}

function formatMetric(value: number | null, digits = 3) {
  return value === null || value === undefined ? "—" : value.toFixed(digits);
}

async function apiRequest<T>(path: string, options?: RequestInit): Promise<T> {
  if (!API_BASE_URL) {
    throw new Error("尚未配置 VITE_API_BASE_URL。请在 Vercel 或本地环境变量中设置 Modal API 地址。");
  }

  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.detail ?? detail;
    } catch {
      // Keep the HTTP status when the response is not JSON.
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

function App() {
  const [target, setTarget] = useState("ESR1");
  const [count, setCount] = useState(1);
  const [runDocking, setRunDocking] = useState(true);
  const [task, setTask] = useState<Task | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);
  const [submittedWithDocking, setSubmittedWithDocking] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const pollTimer = useRef<number | null>(null);

  const running = submitting || (!!taskId && task?.status !== "completed" && task?.status !== "failed");
  const activeStage = displayStageFor(task?.status ?? "queued", submittedWithDocking);
  const activeStageIndex = DISPLAY_STAGES.indexOf(activeStage);

  const visibleStages = useMemo(
    () => (submittedWithDocking ? DISPLAY_STAGES : DISPLAY_STAGES.filter((stage) => stage !== "docking")),
    [submittedWithDocking],
  );

  useEffect(() => {
    if (!taskId) return;

    let cancelled = false;

    const poll = async () => {
      try {
        const nextTask = await apiRequest<Task>(`/api/tasks/${taskId}`);
        if (cancelled) return;
        setTask(nextTask);
        setError(nextTask.status === "failed" ? nextTask.error ?? "任务执行失败。" : null);

        if (nextTask.status !== "completed" && nextTask.status !== "failed") {
          pollTimer.current = window.setTimeout(poll, 3000);
        }
      } catch (pollError) {
        if (cancelled) return;
        setError(pollError instanceof Error ? pollError.message : "无法获取任务状态。");
        pollTimer.current = window.setTimeout(poll, 6000);
      }
    };

    poll();
    return () => {
      cancelled = true;
      if (pollTimer.current !== null) window.clearTimeout(pollTimer.current);
    };
  }, [taskId]);

  const startGeneration = async (event: FormEvent) => {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    setTask(null);
    setTaskId(null);
    setSubmittedWithDocking(runDocking);

    try {
      const response = await apiRequest<GenerateResponse>("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target, num_samples: count, run_docking: runDocking }),
      });
      setTaskId(response.task_id);
      setTask({
        task_id: response.task_id,
        target,
        status: response.status,
        progress: 0,
        current_stage: response.message,
        error: null,
        requested: count,
        generated: 0,
        valid: 0,
        returned: 0,
        candidates: [],
      });
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "任务提交失败。");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="app-shell">
      <header className="site-header">
        <a className="brand" href="#top" aria-label="AI Drug Design Agent 首页">
          <span className="brand-mark" aria-hidden="true">AI</span>
          <span>
            <strong>Drug Design Agent</strong>
            <small>GPU molecular discovery workspace</small>
          </span>
        </a>
        <div className="system-badge"><span /> Modal GPU API</div>
      </header>

      <main id="top">
        <section className="hero">
          <div>
            <p className="eyebrow">Target-guided molecular generation</p>
            <h1>从蛋白靶点出发，<br /><span>生成并筛选候选分子。</span></h1>
            <p className="hero-copy">
              ESM-2 编码蛋白序列，DLPS-E2PO 生成分子，RDKit 验证化学性质，AutoDock Vina 评估结合潜力。
            </p>
          </div>
          <div className="pipeline" aria-label="推理流程">
            {[
              ["01", "ESM-2", "Protein encoding"],
              ["02", "DLPS-E2PO", "Molecule generation"],
              ["03", "RDKit + Vina", "Evaluate & dock"],
            ].map(([number, title, subtitle]) => (
              <div className="pipeline-item" key={number}>
                <span>{number}</span><strong>{title}</strong><small>{subtitle}</small>
              </div>
            ))}
          </div>
        </section>

        <section className="workspace-grid">
          <form className="control-panel" onSubmit={startGeneration}>
            <div className="section-heading">
              <div><span>01</span><h2>生成设置</h2></div>
              <p>选择目标蛋白并设置本次推理任务。</p>
            </div>

            <label className="field-label" htmlFor="target">蛋白靶点</label>
            <div className="select-wrap">
              <select id="target" value={target} onChange={(event) => setTarget(event.target.value)} disabled={running}>
                {TARGETS.map(([name, pdb]) => <option value={name} key={name}>{name} · PDB {pdb}</option>)}
              </select>
            </div>

            <label className="field-label" htmlFor="count">生成数量</label>
            <div className="number-control">
              <button type="button" onClick={() => setCount((value) => Math.max(1, value - 1))} disabled={running || count <= 1} aria-label="减少生成数量">−</button>
              <input id="count" type="number" min="1" max="100" value={count} onChange={(event) => setCount(Math.min(100, Math.max(1, Number(event.target.value) || 1)))} disabled={running} />
              <button type="button" onClick={() => setCount((value) => Math.min(100, value + 1))} disabled={running || count >= 100} aria-label="增加生成数量">+</button>
            </div>

            <label className="toggle-row">
              <span>
                <strong>AutoDock Vina</strong>
                <small>为有效分子执行真实对接评分</small>
              </span>
              <input type="checkbox" checked={runDocking} onChange={(event) => setRunDocking(event.target.checked)} disabled={running} />
              <i aria-hidden="true" />
            </label>

            <button className="submit-button" type="submit" disabled={running || !API_BASE_URL}>
              {running ? <><span className="spinner" />任务执行中</> : <>开始生成 <span>→</span></>}
            </button>
            {!API_BASE_URL && <p className="config-warning">请先配置 VITE_API_BASE_URL。</p>}
          </form>

          <section className="status-panel" aria-live="polite">
            <div className="section-heading">
              <div><span>02</span><h2>任务进度</h2></div>
              {taskId && <code>{taskId.slice(0, 8)}</code>}
            </div>

            {!task ? (
              <div className="empty-state">
                <div className="molecule-orbit"><i /><i /><i /></div>
                <strong>等待生成任务</strong>
                <p>提交后可在这里查看实时阶段与 GPU 推理进度。</p>
              </div>
            ) : (
              <div className="task-state">
                <div className="progress-meta">
                  <span>{task.current_stage}</span>
                  <strong>{Math.round(task.progress)}%</strong>
                </div>
                <div className="progress-track"><div style={{ width: `${task.progress}%` }} /></div>
                <ol className="stage-list">
                  {visibleStages.map((stage) => {
                    const canonicalIndex = DISPLAY_STAGES.indexOf(stage);
                    const done = canonicalIndex < activeStageIndex || task.status === "completed";
                    const active = stage === activeStage && task.status !== "failed";
                    return (
                      <li className={`${done ? "done" : ""} ${active ? "active" : ""}`} key={stage}>
                        <span>{done ? "✓" : canonicalIndex + 1}</span>
                        <div><strong>{STAGE_LABELS[stage]}</strong><small>{stage}</small></div>
                      </li>
                    );
                  })}
                </ol>
                <div className="task-counts">
                  <span>生成 <strong>{task.generated}</strong></span>
                  <span>有效 <strong>{task.valid}</strong></span>
                  <span>返回 <strong>{task.returned}</strong></span>
                </div>
              </div>
            )}
            {error && <div className="error-message" role="alert"><strong>任务异常</strong><span>{error}</span></div>}
          </section>
        </section>

        <section className="results-section">
          <div className="results-header">
            <div>
              <p className="eyebrow">Ranked candidates</p>
              <h2>候选分子</h2>
            </div>
            <span>{task?.candidates.length ?? 0} molecules</span>
          </div>

          {task?.candidates.length ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Rank</th><th>SMILES</th><th>QED</th><th>SA</th><th>MolWt</th><th>LogP</th><th>Lipinski</th><th>Vina score</th></tr></thead>
                <tbody>
                  {task.candidates.map((candidate) => (
                    <tr key={`${candidate.rank}-${candidate.smiles}`}>
                      <td><span className="rank">#{candidate.rank}</span></td>
                      <td><code className="smiles">{candidate.smiles}</code></td>
                      <td>{formatMetric(candidate.qed)}</td>
                      <td>{formatMetric(candidate.sa)}</td>
                      <td>{formatMetric(candidate.molwt, 1)}</td>
                      <td>{formatMetric(candidate.logp, 2)}</td>
                      <td><span className={`pill ${candidate.lipinski ? "pass" : "fail"}`}>{candidate.lipinski === null ? "—" : candidate.lipinski ? "PASS" : "FAIL"}</span></td>
                      <td><strong className="vina-score">{candidate.vina === null ? "—" : `${candidate.vina.toFixed(2)} kcal/mol`}</strong></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="results-empty"><span>∿</span><p>任务完成后，经过 RDKit 验证的候选分子将在此处按评分排序。</p></div>
          )}
        </section>
      </main>

      <footer><span>AI Drug Design Agent</span><span>ESM-2 → DLPS-E2PO → RDKit → AutoDock Vina</span></footer>
    </div>
  );
}

export default App;
