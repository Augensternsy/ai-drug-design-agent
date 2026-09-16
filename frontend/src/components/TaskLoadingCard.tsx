import type { Task } from "../types";

function available(value: number | null): value is number {
  return value !== null && Number.isFinite(value);
}

export function TaskLoadingCard({ task }: { task: Task }) {
  const counts = [
    ["生成", task.generated],
    ["有效", task.valid],
    ["返回", task.returned],
  ] as const;
  const visibleCounts = counts.filter((item) => available(item[1]));

  return (
    <div className="task-loading-card" role="status" aria-live="polite">
      <div className="task-loading-card__animation" aria-hidden="true"><i /><i /><i /></div>
      <div className="task-loading-card__body">
        <p className="eyebrow">Inference in progress</p>
        <h3>正在生成候选分子</h3>
        <p>RTX 3090 正在执行 DLPS-E2PO 推理与性质筛选</p>
        <small>请稍候...</small>
        {(task.current_stage || available(task.progress)) && (
          <div className="task-loading-card__stage">
            {task.current_stage && <span>{task.current_stage}</span>}
            {available(task.progress) && <strong>{Math.round(task.progress)}%</strong>}
          </div>
        )}
        {visibleCounts.length > 0 && <div className="task-loading-card__counts">{visibleCounts.map(([label, value]) => <span key={label}>{label}<strong>{value}</strong></span>)}</div>}
        <div className="task-loading-card__skeleton" aria-hidden="true"><i /><i /><i /></div>
      </div>
    </div>
  );
}
