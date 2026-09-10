# Drug Design Agent — Public Development Skeleton

AI 药物分子设计与筛选 Agent 的公开开发版本。仓库提供 FastAPI 服务、推理流程、RDKit 评价和 AutoDock Vina 对接代码，但不包含模型权重、私密配置、运行输出或大体积数据。

## 系统架构

```text
Vercel / 前端
  → FastAPI GPU API
  → ESM-2 蛋白编码
  → DLPS-E2PO 分子扩散采样
  → RDKit 有效性、性质与多样性筛选
  → AutoDock Vina 分子对接
  → 候选分子结果
```

FastAPI 负责接收蛋白靶点或序列并编排 GPU 推理。ESM-2 生成蛋白表示，DLPS-E2PO 采样 SMILES，RDKit 进行化学有效性和性质筛选，AutoDock Vina 完成对接评分，最后返回排序后的候选分子。

## 最终模型配置

公开版保留以下最终推理配置说明，但不包含对应权重文件：

```ini
checkpoint = models/e2po/direct_ki_e2po_15k.pt
sampling_steps = 200
clamp_mode = none
```

代码中的相关默认值为：

```ini
self_cond = true
vocab_size = 37
max_smiles_len = 170
max_protein_len = 256
```

## 模型权重

模型权重不随 GitHub 发布。部署到云 GPU 时，请通过持久化 Volume 或 Object Storage 下载/挂载权重，并保持配置路径一致。至少需要准备：

- `models/e2po/direct_ki_e2po_15k.pt`
- `models/esm2/` 下的 ESM-2 权重

如需使用 Base 模型，还需另行挂载 `models/base/PLAIN_ema_0.9999_050000.pt`。不要将 `.pt`、`.bin`、`.safetensors` 或其他大模型文件提交到 Git。

## 目录结构

```text
drug-design-agent-public/
├── app/                    # FastAPI、服务层与 Agent 代码
├── scripts/                # 验证与辅助脚本
├── source_backup/          # 推理所需的上游源码快照
├── frontend/               # React + TypeScript + Vite 的 Vercel 前端
├── models/                 # 模型目录骨架、轻量配置与 tokenizer
│   ├── base/
│   ├── e2po/
│   ├── esm2/
│   ├── bert-base-uncased/
│   └── tokenizer/
├── data/                   # 数据目录骨架与挂载说明
│   ├── targets/
│   ├── structures/
│   ├── precomputed/
│   └── references/
├── Dockerfile
├── .dockerignore
├── .env.example
├── .gitignore
├── requirements.txt
└── DEPLOYMENT.md
```

## 本地准备

1. 创建环境配置：

   ```bash
   cp .env.example .env
   ```

2. 将外部权重和所需数据挂载到 `models/`、`data/`，或在 `.env` 中设置绝对路径。

3. 安装依赖并启动 API：

   ```bash
   pip install -r requirements.txt
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

API 文档默认位于 `http://localhost:8000/docs`。

## 安全与发布边界

- `.env`、模型权重、输出、日志、缓存、Python 字节码和临时 docking 文件均被忽略。
- `.env.example` 仅包含示例配置，不应写入真实密钥。
- 本公开版不包含训练权重或运行结果；完整推理依赖外部挂载。
- 本目录由原项目的只读副本整理而来，不应反向覆盖原项目。
