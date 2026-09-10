# RunPod GPU Pod Deployment

This guide deploys the FastAPI service on a RunPod **GPU Pod** with a persistent Network Volume. It does not use RunPod Serverless and does not place model weights in Git or the Docker image.

## Deployment layout

```text
/workspace/                         # RunPod Network Volume mount
├── ai-drug-design-agent/           # Public GitHub repository
├── models/
│   ├── e2po/direct_ki_e2po_15k.pt
│   ├── esm2/
│   ├── bert-base-uncased/config.json
│   └── tokenizer/
├── data/
│   ├── targets/
│   └── structures/
└── logs/
```

The fixed inference settings are:

```ini
checkpoint = models/e2po/direct_ki_e2po_15k.pt
sampling_steps = 200
clamp_mode = none
```

## 1. Create the Network Volume

1. Sign in to RunPod and open **Storage**.
2. Create a Network Volume large enough for the current asset archive and future checkpoints. A 10 GB minimum is practical; allocate more if additional models will be uploaded.
3. Create the volume in the same Secure Cloud datacenter where the GPU Pod will run.

RunPod mounts a Pod Network Volume at `/workspace` by default. Attach it during Pod creation; it cannot be attached to an existing Pod later.

Official references:

- https://docs.runpod.io/storage/network-volumes
- https://docs.runpod.io/pods/storage/types

## 2. Create the GPU Pod

1. Open **Pods** and select **Deploy**.
2. Attach the Network Volume created above.
3. Select an NVIDIA GPU with sufficient memory. The project was designed around an RTX 3090-class 24 GB GPU; use equivalent or larger VRAM when available.
4. Use a RunPod PyTorch template compatible with Python 3.10, PyTorch 2.x and CUDA 11.8. The repository Dockerfile uses:

   ```text
   runpod/pytorch:2.1.0-py3.10-cuda11.8.0-devel-ubuntu22.04
   ```

5. Expose `8000` as an **HTTP port**. Optionally expose `22` as TCP for SSH.
6. Deploy the Pod. Do not enter application secrets directly in shell history; use RunPod Secrets when secrets are later required.

The external API URL has this form:

```text
https://POD_ID-8000.proxy.runpod.net
```

RunPod's HTTP proxy has a 100-second request timeout. This API returns a task ID immediately and exposes `/api/tasks/{task_id}` for polling long GPU jobs.

Official port reference: https://docs.runpod.io/pods/configuration/expose-ports

## 3. Upload the private model/data archive

Upload the locally generated private file `runpod-assets.tar.gz` to the root of the Network Volume. Use the RunPod web file browser, SCP, `runpodctl`, or the Network Volume S3-compatible API.

On the Pod, verify and extract it:

```bash
cd /workspace
sha256sum runpod-assets.tar.gz
tar -xzf runpod-assets.tar.gz -C /workspace
```

Expected archive SHA-256:

```text
31c926aa70e03dfac4939ba1e349f14fa6cabea8ee553c00577b775f2b83d199
```

After extraction:

```bash
test -f /workspace/models/e2po/direct_ki_e2po_15k.pt
test -f /workspace/models/esm2/pytorch_model.bin
test -f /workspace/models/bert-base-uncased/config.json
test -f /workspace/data/targets/targets.json
test -f /workspace/data/structures/2r6w/2r6w_protein_cleaned.pdbqt
```

See `RUNPOD_ASSET_MANIFEST.md` for the complete curated contents.

## 4. Clone the public repository

```bash
cd /workspace
git clone https://github.com/Augensternsy/ai-drug-design-agent.git
cd /workspace/ai-drug-design-agent
git switch main
```

If the repository already exists:

```bash
cd /workspace/ai-drug-design-agent
git pull --ff-only origin main
```

## 5. Configure the environment

```bash
cd /workspace/ai-drug-design-agent
cp .env.runpod.example .env
```

The example already points to `/workspace/models` and `/workspace/data`. Confirm the fixed settings in the application:

```bash
grep -E 'MODEL_PATH|E2PO_CHECKPOINT|ESM_MODEL_PATH|BERT_CONFIG_PATH|TARGET_DATA_PATH|STRUCTURE_DATA_PATH' .env
grep -E 'SAMPLING_STEPS = 200|CLAMP_MODE = "none"' app/config.py
```

Do not commit `.env`.

The natural-language Agent uses its deterministic rules parser by default. To
enable an OpenAI-compatible LLM parser, set `LLM_ENABLED=true`, `LLM_BASE_URL`,
`LLM_API_KEY`, and `LLM_MODEL` only in the Pod's private `.env`. The base URL may
be `/v1` or the complete `/v1/chat/completions` endpoint. Never copy the key into
a frontend `VITE_*` variable.

## 6. Install dependencies and start FastAPI

The bootstrap script validates the volume, NVIDIA GPU, CUDA-enabled PyTorch, ESM-2 dependencies, RDKit, Vina and Meeko before starting Uvicorn:

```bash
cd /workspace/ai-drug-design-agent
bash scripts/runpod_bootstrap.sh
```

The service listens on `0.0.0.0:8000`. To keep it running after disconnecting from the terminal, use `tmux`:

```bash
cd /workspace/ai-drug-design-agent
tmux new -s drug-agent
bash scripts/runpod_bootstrap.sh
```

Detach from tmux with `Ctrl-b`, then `d`. Reattach with:

```bash
tmux attach -t drug-agent
```

## 7. Test `/api/health`

Inside the Pod:

```bash
curl --fail --silent --show-error http://127.0.0.1:8000/api/health
```

Expected fields include:

```json
{
  "status": "ok",
  "cuda_available": true,
  "rdkit_available": true,
  "vina_available": true
}
```

From your local computer, replace the URL with the RunPod proxy URL:

```bash
curl --fail --silent --show-error https://POD_ID-8000.proxy.runpod.net/api/health
```

## 8. Test `/api/generate`

```bash
curl --fail --silent --show-error \
  -X POST http://127.0.0.1:8000/api/generate \
  -H 'Content-Type: application/json' \
  -d '{"target":"ESR1","num_samples":1,"run_docking":false}'
```

The response should contain `status: queued` and a `task_id`. Poll it with:

```bash
curl --fail --silent --show-error \
  http://127.0.0.1:8000/api/tasks/TASK_ID
```

Run both smoke checks automatically:

```bash
bash scripts/runpod_smoke_test.sh http://127.0.0.1:8000
```

To test through the public proxy:

```bash
bash scripts/runpod_smoke_test.sh https://POD_ID-8000.proxy.runpod.net
```

## Docker image alternative

The Dockerfile is ready for a custom RunPod Pod template and deliberately omits weights and data. Build the image on a Docker-capable machine, push it to a container registry, expose port `8000/http`, and attach the same Network Volume at `/workspace`. RunPod Pods do not support Docker Compose or ordinary Docker-in-Docker workflows.
