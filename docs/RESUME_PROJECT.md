# AI 药物分子设计与筛选 Agent

在线 Demo：<https://frontend-augensternsys-projects.vercel.app><br>
GitHub：<https://github.com/Augensternsy/ai-drug-design-agent>

## 中文简历项目描述

- 面向靶点条件分子设计场景，独立搭建 LLM Agent + Tool Calling 编排层，将自然语言需求解析为经 Pydantic 校验的 `AgentPlan`，串联 `resolve_target`、分子生成、性质评价、可选对接、排序与结果总结；在 LLM 未配置、超时、输出非法或校验失败时自动回退规则解析，保证核心流程不依赖单一厂商或外部模型。
- 复用 ESM-2 蛋白表征与 DLPS-E2PO 专业生成模型，封装 RDKit 有效性/QED/SA/MolWt/LogP/Lipinski 评价和 AutoDock Vina 对接工具链；保持论文推理 checkpoint、200 步采样与 `clamp_mode=none` 不变，并明确项目正式验证范围为 12 个测试靶点。
- 基于 FastAPI 实现异步任务创建、阶段状态轮询、Tool trace、错误透传与候选排序；使用 Modal Serverless A10 GPU 和持久化 Volume 承载私有模型/数据，配置单容器、空闲缩容、单次最多 5 个候选、默认关闭 Vina 与请求冷却，兼顾在线 Demo 可用性、Secret 隔离和 GPU 成本控制。
- 使用 React + TypeScript + Vite 构建并部署 Vercel 科研工作台，实现 2D SVG、3Dmol.js 三维构象、SMILES/指标卡片、SDF/CSV/JSON 导出及 localStorage 历史；通过 GitHub 公开工程骨架、部署文档与 mock/unit tests，同时排除模型权重和敏感配置。

## 面试口述版（60–90 秒）

这个项目是我完成的一套 AI 药物分子设计与筛选 Agent，目标是把自然语言交互和专业分子计算工具真正串成一个可在线演示的工程。用户既可以填表，也可以直接描述靶点、生成数量、QED 或 SA 约束以及是否进行 Vina 对接。我实现了厂商无关的 OpenAI-compatible LLM 解析层，把请求转换成 Pydantic 校验的 Agent Plan；如果没有 Key、调用超时、JSON 不合法或 schema 校验失败，会自动回退到规则解析器。

后续工具链没有让 LLM 替代专业模型，而是继续复用 ESM-2 做蛋白表征、DLPS-E2PO 做条件分子生成，再用 RDKit 计算性质和生成 2D/3D 数据，按需调用 AutoDock Vina，最后排序并输出总结。后端用 FastAPI 异步任务和轮询状态，部署在 Modal Serverless A10 GPU 上；前端用 React、TypeScript 和 Vite 部署到 Vercel，并支持 3Dmol.js、结果导出和本地历史。为了控制公开 Demo 成本，我加入了 5 个分子的硬上限、Vina 默认关闭、提交确认、限流和自动缩容。科研上我也明确限定：目前正式验证的是 12 个测试靶点，不把结果外推成任意靶点都可靠。
