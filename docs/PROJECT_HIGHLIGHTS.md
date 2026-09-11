# 项目亮点与面试准备

## 项目背景

靶点条件分子设计涉及蛋白表征、生成模型、化学性质评价、分子对接和结果解释。单独运行这些组件不仅操作割裂，也难以向非模型开发者展示每一步的输入、状态和失败原因。本项目将已有科研模型与工具封装为可观察的 Agent 工作流和在线 Demo。

## 我负责的内容

- 整理公开工程骨架、依赖、资产挂载规范和 GitHub 文档。
- 将现有生成、评价、对接与排序能力封装为 Agent Tools。
- 实现 OpenAI-compatible LLM Parser、Pydantic AgentPlan 和 rule fallback。
- 构建 FastAPI 异步任务、状态轮询、Tool trace、参数校验和错误处理。
- 构建 React + TypeScript + Vite 前端、2D/3D 分子卡片、导出和本地历史。
- 准备 Modal Serverless GPU、Volume、Secret，以及 RunPod 备选部署方案。
- 增加单次上限、Vina 默认关闭、cooldown、按钮锁定和 autoscaling-to-zero 等成本保护。

## 核心难点

1. 在不修改 DLPS-E2PO 算法的前提下，把模型脚本封装成稳定服务。
2. 让 LLM 只做编排，同时阻止非法 target、数量和约束进入 GPU 工具链。
3. 兼容旧科研代码依赖、CUDA、ESM-2、RDKit、Meeko 和 Vina。
4. 在 Serverless GPU 冷启动和长任务条件下提供可观察状态。
5. 将模型权重、结构数据和 API Key 与公开 GitHub/Vercel 边界隔离。
6. 在作品 Demo 的可用性与 GPU/对接成本之间取得平衡。

## 技术选型原因

| Choice | Reason |
| --- | --- |
| FastAPI + Pydantic | 适合 Python 模型栈；请求与 AgentPlan 可以统一校验并返回明确 4xx |
| OpenAI-compatible HTTP | 不绑定单一 LLM 厂商，也无需在前端集成密钥或 SDK |
| Rule fallback | LLM 配置缺失或外部服务失败时，常见中文任务仍可确定性解析 |
| Modal Serverless GPU | 适合作品 Demo 的按需 GPU、Web Endpoint、Volume、Secret 和空闲缩容 |
| React + TypeScript + Vite | 快速构建类型明确的交互式科研工作台并部署到 Vercel |
| RDKit + 3Dmol.js | 后端生成可靠的化学结构数据，前端无需付费服务即可展示 2D/3D |
| localStorage | 最近任务只需本地恢复，不为作品 Demo 引入数据库运维成本 |

## 关键问题与解决方案

- **LLM 输出不稳定：** 强制结构化 JSON，随后执行 Pydantic 校验；任何异常进入 rule fallback。
- **中文否定语义：** 对“不进行 Vina 对接”等否定表达设置高于关键词命中的优先级，并补充 UTF-8 回归测试。
- **Modal 依赖不一致：** Secret 改为模块级固定对象并始终挂载，保证本地 deploy 和远程 hydrate 依赖列表一致。
- **旧 Transformers 内部 API：** 对迁移后的工具函数使用新路径优先、旧路径 fallback，并锁定兼容版本。
- **Vina 失败不可见：** 将可执行文件、受体、临时目录、子进程 stderr 和输出路径错误写入任务日志。
- **公开仓库过大或泄密：** 权重与完整数据通过 Volume/Object Storage 挂载，`.gitignore` 排除 Secret、checkpoint、缓存和输出。
- **GPU 冷启动：** 使用异步任务、轮询、阶段状态和友好提示，避免长请求表现为前端无响应。

## 工程亮点

- Agent 层与专业模型层职责分离，可替换 LLM Provider 而不改生成算法。
- 前后端同时校验，但以后端 Pydantic/白名单为安全边界。
- 任务返回 Agent Plan、Tool trace、阶段、错误和候选结果，便于演示与诊断。
- mock/unit tests 覆盖 LLM 成功、超时、HTTP 错误、JSON/schema 失败、中文语义和成本限制。
- README、部署文档、资产清单、截图清单和演示脚本形成完整交付材料。

## Agent 设计亮点

Agent 的价值不是“用了 LLM”，而是把自然语言意图转换成受约束的工具调用计划。LLM 无权绕过靶点白名单、数量上限或 Pydantic 校验；它也不直接计算 QED、Vina 或 SMILES。相同 AgentPlan 可以来自 LLM 或规则解析器，并进入同一工具链，因此 fallback 不会产生第二套业务实现。

## 部署亮点

- Vercel 与 Modal 通过公开 HTTPS API 解耦。
- 模型和数据保存在 `ai-drug-design-assets` Volume，不进入镜像和 GitHub。
- LLM Key 保存在 `ai-drug-design-agent-llm` Secret，不进入前端或日志。
- Serverless GPU 空闲缩容到 0，且公开 Demo 限制最大一个 GPU 容器。
- RunPod + Network Volume 保留为需要常驻或更强控制时的备选方案。

## 面试常见问题与参考答案

### 1. 为什么用 Agent，而不是普通固定工作流？

底层工具调用顺序本身是受控工作流；Agent 增加的是自然语言理解、参数提取、条件分支、Tool trace 和结果总结。用户可以表达 QED/SA、数量和是否对接，而系统仍把执行限制在白名单工具和 Pydantic schema 内。

### 2. LLM 在项目里具体负责什么？

只负责把自然语言解析为 target、num_samples、QED/SA 约束、是否 Vina 和 dock_top_k。它不生成分子、不计算 RDKit 指标、不运行 Vina，也不修改模型配置。

### 3. 为什么要 rule fallback？

LLM 可能没有 Key、超时、产生非法 JSON 或违反 schema。规则解析覆盖作品 Demo 中最常见的明确指令，使任务理解不被单一外部服务卡住，并让失败行为可预测、可测试。

### 4. 为什么还要 Pydantic 校验 LLM 输出？

LLM 输出是不可信输入。Pydantic 统一限制数量、阈值范围、字段类型和可选值；靶点还要经过白名单解析。这样即使 LLM 理解错误，也不能直接把危险参数传给 GPU。

### 5. 为什么使用 Modal？

作品 Demo 的访问不连续。Modal 同时提供按需 GPU、ASGI Web Endpoint、持久化 Volume、Secret 和空闲缩容，能把前端体验与本地 GPU 环境分离，并减少空闲成本。

### 6. 为什么使用异步任务而不是同步等待？

模型加载、采样、RDKit 评价和 Vina 的耗时差异大，还可能包含 GPU 冷启动。异步任务先返回 task_id，前端轮询阶段和错误，避免长 HTTP 请求超时，也提高可观察性。

### 7. 如何控制 GPU 成本？

前后端限制单次最多 5 个候选，Vina 默认关闭，生成前确认，运行中锁定按钮，设置 cooldown；Modal 使用 `min_containers=0`、`max_containers=1`，空闲缩容到 0。高流量场景还需网关配额和持久化限流。

### 8. 如何保证 API Key 安全？

LLM Key 只存在 Modal Secret。Vercel 只获得公开 API Base URL；代码、`.env.example`、GitHub、响应和日志都不保存完整 Key，诊断只显示 `LLM_API_KEY_PRESENT=true/false`。

### 9. 为什么 Vina 是可选的？

Vina 比常规性质计算更耗时，并依赖受体结构、口袋范围、配体构象和参数。默认关闭更适合公开 Demo；需要时可只对排名靠前的少量候选执行。

### 10. 12 个靶点的范围怎么解释？

12 个靶点是当前论文实验正式验证范围，也是公开 Demo 白名单。它说明工程链路在这组测试对象上完成验证，不代表所有蛋白或新序列都有相同可靠性。

### 11. 如何扩展到任意蛋白序列？

工程上可增加序列输入、长度/字符校验、ESM-2 编码和资产策略；科研上还必须做适用域判断、结构/口袋准备、基准集评估和湿实验验证。因此只能说“支持输入能力扩展”，不能直接说“任意靶点可靠”。

### 12. 如何处理 LLM 与专业模型的职责冲突？

通过接口边界解决：LLM 只能输出 AgentPlan；生成工具内部固定调用 ESM-2 和 DLPS-E2PO，评价和对接分别由 RDKit 与 Vina 完成。专业结果不由 LLM臆测。

### 13. 如果 Modal 或 LLM 挂了，用户看到什么？

LLM 失败会进入 rules parser；GPU/API 失败则通过 task status 和明确错误展示，不伪造结果。前端 Demo UI 可以展示交互，但必须标记为 mock，不能冒充在线推理。

### 14. 当前方案还有哪些生产化缺口？

内存任务状态和 cooldown 只适合作品 Demo。生产环境应增加身份认证、持久化队列/任务存储、分布式限流、审计、配额、监控告警和更系统的模型/科研验证。

## 事实边界

- 已完成的真实生成与 Vina 测试证明工程链路可运行，不等同于湿实验活性验证。
- 当前不提供虚构的 QPS、准确率、命中率、用户数或性能提升数据。
- Modal Academic Credits 正在审核；该状态不应描述为已获得额度。
