# AI 药物分子设计 Agent

面向科研展示与在线体验的靶点条件分子生成系统。用户可以通过参数表单或自然语言描述设计需求；Agent 将需求解析为受约束的工作流，并复用现有 ESM-2、DLPS-E2PO、RDKit 与 AutoDock Vina 能力完成生成、评价、对接和排序。

> 科研边界：当前论文实验验证范围为下文列出的 **12 个测试靶点**。本项目不宣称对任意蛋白靶点均可靠，生成与对接结果也不能替代湿实验、临床判断或药物安全性评估。

## 在线 Demo

- Vercel 前端：<https://frontend-augensternsys-projects.vercel.app>
- GitHub：<https://github.com/Augensternsy/ai-drug-design-agent>

公开 Demo 使用 Modal Serverless GPU，空闲时缩容到 0。首次请求可能经历镜像与模型冷启动；为控制公开演示成本，每个任务最多生成 5 个候选分子，Vina 默认关闭，并设置提交冷却。

## 截图

> 截图占位：部署新版 Vercel 与 Modal 后，在此放置 `docs/screenshots/agent-workspace.png`（Agent 工作流）和 `docs/screenshots/molecule-cards.png`（2D/3D 候选卡片）。

## 系统架构

```text
Vercel / React 前端
  ├─ 参数表单
  └─ 自然语言 Agent 输入
          ↓
FastAPI Agent Orchestration
  → resolve_target
  → generate_molecules
  → evaluate_properties
  → molecular_docking（可选）
  → rank_candidates
  → generate_result_summary
          ↓
Modal Serverless GPU / RunPod Pod
  → ESM-2 蛋白表示
  → DLPS-E2PO 条件分子生成
  → RDKit 有效性、性质、2D SVG 与 3D SDF
  → AutoDock Vina 对接评分
          ↓
候选分子卡片、导出文件与浏览器本地任务历史
```

### Agent orchestration 与专业生成模型

- **Agent orchestration** 只负责理解用户意图、验证参数、选择工具、跟踪阶段和总结结果；它不会修改生成模型。
- **DLPS-E2PO** 是专业分子生成模型，接受 ESM-2 蛋白表示并执行固定扩散采样。
- 没有 LLM Key 时，Agent 使用内置规则解析器，示例中文指令仍可运行。
- 配置 OpenAI-compatible Provider 后，LLM 只用于结构化意图解析；所有输出仍经过 Pydantic、靶点白名单与样本上限验证。

示例：

```text
帮我针对 ESR1 生成 5 个候选分子，QED 优先，SA<3.5，并对最优结果进行 Vina 对接。
```

解析结果：`target=ESR1`、`num_samples=5`、`sa_threshold=3.5`、`qed_priority=true`、`run_docking=true`、`dock_top_k=1`。

## Agent Tools

| Tool | 复用能力 | 作用 |
| --- | --- | --- |
| `resolve_target` | `TargetRegistry` | 解析并校验 12 靶点白名单 |
| `generate_molecules` | `model_service` / Demo 数据 | 调用现有 DLPS-E2PO 生成能力 |
| `evaluate_properties` | `eval_service` + RDKit | 有效性、QED、SA、MolWt、LogP、Lipinski |
| `molecular_docking` | `docking_service` | 调用现有 AutoDock Vina 流程 |
| `rank_candidates` | 现有评价结果 | 有 Vina 时按对接分数，否则按 QED 排序 |
| `generate_result_summary` | 任务结果 | 生成简洁、可追溯的结果总结 |

## 固定推理配置

公开版本不包含权重，但保持最终推理配置不变：

```ini
checkpoint = models/e2po/direct_ki_e2po_15k.pt
sampling_steps = 200
clamp_mode = none
```

模型权重通过持久化 Volume 或 Object Storage 挂载，不提交 GitHub。

## 技术栈

- 前端：React 19、TypeScript、Vite、3Dmol.js、Vercel
- API 与编排：FastAPI、Pydantic、规则解析、可选 OpenAI-compatible LLM
- 表征与生成：ESM-2、DLPS-E2PO、PyTorch、CUDA
- 化学信息学：RDKit（性质、2D SVG、3D conformer、SDF）
- 分子对接：Meeko、AutoDock Vina
- 云 GPU：Modal Serverless GPU；保留 RunPod Pod + Network Volume 方案

## 12 个测试靶点

| Target | PDB | Target | PDB |
| --- | --- | --- | --- |
| ESR1 | 2R6W | HCRTR1 | 4ZJC |
| JAK1 | 3EYG | P2RX3 | 5SVL |
| KDM1A | 5LHG | IDH1 | 4UMX |
| RIOK1 | 4OTP | NR4A1 | 3V3Q |
| GRIK1 | 3FV1 | CCR9 | 5LWE |
| FTO | 4ZS3 | SPIN1 | 5JSJ |

这些靶点具有项目所需的测试序列和对接结构资产。后续即使增加蛋白序列输入，也必须重新评估适用域与可靠性，不能直接外推为“任意靶点均可靠”。

## 前端能力

- 参数表单与自然语言 Agent 两种入口
- queued / generating / evaluating / docking / completed 状态和 Agent Tool trace
- 单分子结果卡片：SMILES、QED、SA、MolWt、LogP、Lipinski、Vina score、Rank
- RDKit 2D SVG 与可展开 3Dmol.js 三维构象
- Copy SMILES、单分子 SDF、全部 SDF、CSV 与 JSON 导出
- `localStorage` 保存最近 6 个任务，可重新查看，无数据库依赖
- Live / Demo 状态、GPU 冷启动与失败提示、移动端布局

## 本地运行

### 后端

```bash
cp .env.example .env
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

将私有资产挂载到 `.env` 配置的 `models/` 与 `data/` 路径。API 文档位于 `http://127.0.0.1:8000/docs`。

规则 Agent 请求：

```bash
curl -X POST http://127.0.0.1:8000/api/agent/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt":"帮我针对 ESR1 生成 3 个候选分子，QED 优先，不进行 Vina 对接"}'
```

### 可选 LLM Provider

`.env` 中配置以下变量；不要提交真实值：

```ini
LLM_PROVIDER=openai_compatible
LLM_API_BASE_URL=https://provider.example/v1
LLM_MODEL=model-name
LLM_API_KEY=your-private-key
LLM_TIMEOUT_SECONDS=10
```

缺少任一项时自动使用规则解析。`LLM_API_KEY` 只能存在于后端环境或 Modal Secret，绝不能使用 `VITE_*` 前缀。

### 前端

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

生产构建：

```bash
npm run build
```

前端只需要公开的 API Origin：

```ini
VITE_API_BASE_URL=https://your-api.example
```

## 云部署

- Modal Serverless GPU：[MODAL_DEPLOYMENT.md](MODAL_DEPLOYMENT.md)
- RunPod Pod + Network Volume：[RUNPOD_DEPLOYMENT.md](RUNPOD_DEPLOYMENT.md)
- Vercel 前端：[VERCEL_DEPLOYMENT.md](VERCEL_DEPLOYMENT.md)
- 私有模型/数据清单：[RUNPOD_ASSET_MANIFEST.md](RUNPOD_ASSET_MANIFEST.md)

Modal 挂载路径保持：

```text
/workspace/models
/workspace/data
```

## 安全与成本保护

- 前后端均限制 `num_samples <= 5`；Pydantic 和 API 进行二次验证。
- Vina 默认关闭；Agent 可只对 QED 最优的 1 个候选执行对接。
- 提交前确认、运行中按钮锁定和 15 秒前端冷却，减少误触与重复点击。
- FastAPI 生成端点提供按客户端的服务端冷却，并对非法靶点、阈值、数量返回明确 4xx。
- Modal `max_containers=1`、`min_containers=0`，空闲自动缩容到 0。
- 前端不包含 Modal Token、LLM Key 或其他 Secret；仅保存公开 API 地址。
- `.env`、权重、数据、输出、日志、缓存和临时 docking 文件由 `.gitignore` 排除。
- Demo fallback 保持可用；LLM 不可用不会阻断规则解析。
- 内存冷却适合个人作品 Demo，不等价于企业级 WAF。高流量公开服务应在 API Gateway 再配置配额、身份验证与持久化限流。

## 测试（不调用 GPU）

```bash
python -m compileall app tests
python -m unittest discover -s tests -v
cd frontend && npm run build
```

上述单元测试只覆盖规则解析、参数保护、冷却与纯排序逻辑，不调用 Modal API、不执行真实生成或 Vina。
