# AI 药物分子设计与筛选 Agent

- 在线 Demo：<https://frontend-augensternsys-projects.vercel.app>
- GitHub：<https://github.com/Augensternsy/ai-drug-design-agent>
- 目标岗位：Agent 开发 / AI 应用开发 / 算法工程师

## A. 简历正式版

- 面向靶点条件分子设计流程割裂、专业工具使用门槛高的问题，独立实现 LLM Agent + Tool Calling 编排层，将自然语言解析为经 Pydantic 校验的 `AgentPlan`，串联靶点解析、分子生成、性质评价、可选对接、排序和总结；在 Key 缺失、HTTP 失败、超时、JSON 或 schema 异常时自动切换 rule fallback，保证任务理解不依赖单一 LLM 服务。
- 在不改动专业模型算法的前提下，复用 ESM-2 蛋白表征与 DLPS-E2PO 条件生成模型，封装 RDKit Validity/QED/SA/MolWt/LogP/Lipinski 评价、2D/3D 数据生成和 AutoDock Vina 对接链路；固定论文 checkpoint、200 步采样与 `clamp_mode=none`，并将科研结论严格限定为 12 个正式测试靶点。
- 基于 FastAPI 构建异步任务接口和阶段轮询，输出 Agent Plan、Tool trace、失败原因与候选排名；通过 Modal Serverless GPU、持久化 Volume 和 Secret 隔离私有模型/数据/Key，并加入单次最多 5 个候选、Vina 默认关闭、cooldown、后端参数校验和空闲缩容到 0 等成本保护。
- 使用 React、TypeScript、Vite 和 3Dmol.js 构建并部署 Vercel 科研工作台，实现移动端适配、键盘可访问、状态反馈、2D/3D 分子卡片、SDF/CSV/JSON 导出及 localStorage 历史；通过 GitHub 发布可运行工程骨架、mock/unit tests 与 Modal/RunPod/Vercel 部署文档。

## B. 60 秒面试口述版

我做的是一套 AI 药物分子设计与筛选 Agent，重点不是让大语言模型直接生成分子，而是让它理解用户的靶点、数量、QED/SA 约束和是否对接，并转换成经过 Pydantic 校验的 Agent Plan。随后 Agent 依次调用靶点解析、ESM-2、DLPS-E2PO、RDKit、可选 AutoDock Vina、排序和结果总结工具。如果 LLM 没有 Key、超时或返回格式错误，会自动回退规则解析。

工程上我用 FastAPI 做异步任务和状态轮询，用 Modal Serverless GPU 与 Volume 承载私有模型和数据，前端使用 React、TypeScript、Vite 部署在 Vercel，并提供 2D/3D 查看、结果导出和本地历史。公开 Demo 增加了 5 个分子的硬上限、Vina 默认关闭、cooldown、后端校验和 Secret 隔离。科研上我只表述论文正式验证过的 12 个测试靶点，不把工程扩展能力等同于任意靶点可靠。

## C. 90 秒面试口述版

这个项目来自靶点条件分子设计流程中模型、化学评价和对接工具彼此割裂的问题。我希望用户既能通过表单，也能直接用自然语言描述任务，例如针对 ESR1 生成候选、限制 SA，并只对最优结果做 Vina。我的实现把大语言模型放在编排层：它只解析 target、num_samples、QED/SA 和 docking 意图，输出 Pydantic 校验的 Agent Plan，不替代专业生成模型。任何配置缺失、网络超时、HTTP 错误、非法 JSON 或校验失败都会进入确定性 rule fallback。

执行层继续复用 ESM-2 做蛋白表征、DLPS-E2PO 做条件分子生成，再由 RDKit 检查结构有效性、计算 QED、SA、MolWt、LogP 和 Lipinski，并生成 2D SVG 与 3D SDF；AutoDock Vina 是按需工具，完成后再统一排序和生成任务总结。后端使用 FastAPI 异步任务、轮询和 Tool trace，使 GPU 冷启动、生成、评价、对接和失败阶段对前端可见。

部署上我把 React + TypeScript + Vite 前端放在 Vercel，把 GPU API 放在 Modal，模型和结构数据保存在 Volume，LLM Key 只放 Modal Secret。为控制公开 Demo 成本，我实现单次最多 5 个候选、Vina 默认关闭、提交确认、cooldown、后端二次校验、单 GPU 容器和空闲缩容到 0。当前论文正式验证范围是 12 个测试靶点；如果未来加入任意序列输入，还需要做适用域和实验验证，不能直接宣称可靠。

## 表述边界

- 不使用未经验证的 QPS、准确率、活性命中率、用户量或性能提升数据。
- “完成真实生成与 Vina 链路验证”只说明工程链路可运行，不等于候选已获得湿实验活性验证。
- “支持扩展蛋白序列输入”不等于“任意靶点均可靠”。
