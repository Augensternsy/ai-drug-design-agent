# Screenshot Checklist

当前 `docs/images/` 中只有本地 Vite + mock 数据生成的 UI 预览：

- `dashboard.png`：前端主页面
- `agent-workflow.png`：任务状态与 Agent Tools
- `molecule-result.png`：结果卡片与 2D 结构

这些图片已在 README 中明确标记为 mock UI，不得描述为真实模型结果。

## Modal Academic Credits 通过后需要人工补截

仅执行一次受控 ESR1 演示任务，并依次保存：

| Required screenshot | Suggested filename | 必须包含 |
| --- | --- | --- |
| 真实 Agent 计划与工作流 | `agent-plan-live.png` | 原始 Prompt、`parser=llm`、target、num_samples、否定 Vina 语义或 docking 计划 |
| 真实候选分子结果 | `generation-result-live.png` | completed 状态、真实 SMILES、Rank、RDKit Valid |
| 真实 Vina 结果 | `vina-result-live.png` | ESR1、`run_docking=true`、非空 Vina score；只需单分子一次 |
| 真实 2D 分子卡片 | `molecule-2d-live.png` | 2D 结构、SMILES、QED、SA、MolWt、LogP、Lipinski |
| 真实 3D 展开视图 | `molecule-3d-live.png` | 3Dmol.js 查看区域和对应候选编号 |
| 完整前端主页面 | `dashboard-live.png` | LIVE 状态、输入区域、工作台整体布局 |

## 截图前检查

- 隐藏浏览器收藏栏、个人账号、Modal 控制台余额和通知。
- 不截取 Modal Secret、API Key、Token、`.env`、请求 Header 或内部对象 ID。
- 不修改真实结果，不用 mock 分数替换 Vina score。
- 保留靶点、任务状态和指标上下文，避免只截一个无法验证来源的数字。
- 推荐统一使用 1440×900 或更高分辨率，PNG 格式。
- 如公开任务失败，保留日志用于诊断，不把失败结果包装成成功截图。

## README 替换方式

截图完成后，将真实图片放入 `docs/images/`，在 README 的 Demo Screenshots 表格中引用，并删除对应“待补截”说明。保留 mock 图时必须继续标注 `mock UI`。
