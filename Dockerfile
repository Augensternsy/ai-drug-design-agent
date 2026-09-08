# RunPod-compatible CUDA/PyTorch image for the FastAPI GPU backend.
FROM runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_DIR=/app \
    RUNPOD_SKIP_INSTALL=1 \
    DEVICE=cuda \
    INFERENCE_MODE=local \
    MODEL_PATH=/workspace/models/e2po/direct_ki_e2po_15k.pt \
    E2PO_CHECKPOINT=/workspace/models/e2po/direct_ki_e2po_15k.pt \
    ESM_MODEL_PATH=/workspace/models/esm2 \
    TOKENIZER_PATH=/workspace/models/tokenizer \
    BERT_CONFIG_PATH=/workspace/models/bert-base-uncased \
    TARGET_DATA_PATH=/workspace/data/targets/fasta \
    STRUCTURE_DATA_PATH=/workspace/data/structures \
    DEMO_DATA_PATH=/workspace/data/demo \
    HOST=0.0.0.0 \
    PORT=8000

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

# Model weights and data are deliberately not copied into the image.
COPY app ./app
COPY source_backup ./source_backup
COPY scripts ./scripts
COPY .env.runpod.example ./.env.runpod.example

RUN mkdir -p /workspace/models /workspace/data /workspace/logs /app/outputs

EXPOSE 8000

CMD ["bash", "scripts/runpod_bootstrap.sh"]
