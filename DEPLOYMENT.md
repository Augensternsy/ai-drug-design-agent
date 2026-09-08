# Deployment and External Model Mounting

RunPod GPU Pod 的完整部署流程见 [`RUNPOD_DEPLOYMENT.md`](RUNPOD_DEPLOYMENT.md)。

本公开版本只提供代码和轻量配置，不包含模型权重。Vercel 适合托管前端；FastAPI、ESM-2、DLPS-E2PO、RDKit 和 AutoDock Vina 应运行在带 GPU 的后端环境中。

## 部署拓扑

```text
Vercel / frontend
  → HTTPS
  → FastAPI GPU API
  → ESM-2
  → DLPS-E2PO
  → RDKit
  → AutoDock Vina
  → candidate molecules
```

## 固定推理配置

```ini
checkpoint = models/e2po/direct_ki_e2po_15k.pt
sampling_steps = 200
clamp_mode = none
```

不要把 checkpoint 加入 Docker 镜像或 Git 仓库。

## 环境准备

```bash
cp .env.example .env
pip install -r requirements.txt
```

根据部署环境修改 `.env` 中的路径。`.env` 仅用于本地或部署平台的 Secret 管理，不得提交。

## Volume 挂载

将持久化 Volume 挂载到容器的 `/app/models`。目录至少应包含：

```text
/app/models/
├── e2po/direct_ki_e2po_15k.pt
└── esm2/<ESM-2 model files>
```

Docker 示例：

```bash
docker build -t drug-design-agent-public .
docker run --gpus all \
  -p 8000:8000 \
  --env-file .env \
  -v /path/to/persistent/models:/app/models \
  -v /path/to/persistent/data:/app/data \
  drug-design-agent-public
```

## Object Storage

如果平台使用 S3、R2 或兼容对象存储，应在容器启动前把权重同步到持久化 Volume 或受控本地缓存，再通过环境变量指向实际路径。不要在应用请求处理中重复下载大模型。

推荐环境变量：

```ini
MODEL_PATH=/app/models/e2po/direct_ki_e2po_15k.pt
E2PO_CHECKPOINT=/app/models/e2po/direct_ki_e2po_15k.pt
ESM_MODEL_PATH=/app/models/esm2
TOKENIZER_PATH=/app/models/tokenizer/vocab.json
TARGET_DATA_PATH=/app/data/targets
STRUCTURE_DATA_PATH=/app/data/structures
```

## 启动 API

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- Swagger UI: `http://localhost:8000/docs`
- Redoc: `http://localhost:8000/redoc`

## 部署检查

- GPU 容器能识别 CUDA。
- checkpoint 和 ESM-2 路径可读。
- `sampling_steps` 为 `200`，`clamp_mode` 为 `none`。
- Vina 可执行文件可通过 `VINA_PATH` 调用。
- 输出、日志和临时 docking 文件写入持久化工作目录，但不进入 Git。
