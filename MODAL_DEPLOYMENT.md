# Modal Serverless GPU Deployment

This deployment keeps the existing FastAPI and inference implementation intact:

```text
Vercel / web frontend
  -> Modal HTTP API
  -> ESM-2
  -> DLPS-E2PO
  -> RDKit
  -> AutoDock Vina
  -> candidate molecules
```

Modal mounts the private asset Volume at `/workspace`. The API uses one 24 GB A10 GPU container at most and `min_containers=0`, so it scales to zero when idle. The first request after scale-to-zero has a cold start while the image and models load.

## Fixed inference configuration

Do not change these release settings:

```text
checkpoint = models/e2po/direct_ki_e2po_15k.pt
sampling_steps = 200
clamp_mode = none
```

The Modal runtime resolves the checkpoint at `/workspace/models/e2po/direct_ki_e2po_15k.pt`. Model weights and target data are not committed to GitHub.

## 1. Install and authenticate Modal on Windows

Open PowerShell and run:

```powershell
Set-Location 'E:\blog\AIProjects\drug-design-agent-public'
py -m pip install --upgrade modal
py -m modal setup
```

`modal setup` opens a browser for account authentication and stores a local Modal token.

## 2. Create the asset Volume

Create the named Volume once:

```powershell
py -m modal volume create ai-drug-design-assets
```

The same Volume is mounted by `modal_app.py` at `/workspace`, yielding:

```text
/workspace/models/
/workspace/data/
```

## 3. Upload and extract the existing private asset archive

The existing archive is reusable without repacking. Its required SHA-256 is:

```text
31c926aa70e03dfac4939ba1e349f14fa6cabea8ee553c00577b775f2b83d199
```

Run the helper from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\modal_upload_assets.ps1 `
  -AssetPath 'E:\blog\AIProjects\runpod-assets.tar.gz' `
  -VolumeName 'ai-drug-design-assets'
```

The helper verifies the local SHA-256, uploads the archive as `/runpod-assets.tar.gz`, and invokes the CPU-only `extract_assets` Modal Function. That Function verifies the hash again, rejects unsafe tar paths, extracts `models/` and `data/`, checks critical files, and commits the Volume. It does not request a GPU.

Inspect the uploaded layout if needed:

```powershell
py -m modal volume ls ai-drug-design-assets /models
py -m modal volume ls ai-drug-design-assets /data
```

Critical paths after extraction:

```text
/workspace/models/e2po/direct_ki_e2po_15k.pt
/workspace/models/esm2/pytorch_model.bin
/workspace/models/bert-base-uncased/config.json
/workspace/models/tokenizer/mytokenizers.py
/workspace/data/targets/fasta/<TARGET>.fasta
/workspace/data/structures/<PDB_ID>/<PDB_ID>_protein_cleaned.pdbqt
/workspace/data/structures/<PDB_ID>/<PDB_ID>_ligand.sdf
```

## 4. Review optional Modal settings

`.env.modal.example` documents the defaults. `modal_app.py` reads the four `MODAL_*` values from the PowerShell environment at deploy time. The defaults already match this guide; no environment export is required.

To override a deployment setting for the current PowerShell session, use commands such as:

```powershell
$env:MODAL_VOLUME_NAME = 'ai-drug-design-assets'
$env:MODAL_GPU = 'A10'
$env:MODAL_SCALEDOWN_WINDOW = '300'
```

Do not override the fixed checkpoint, sampling steps, or clamp mode.

The natural-language Agent works without an LLM key through its deterministic
rules parser. To enable an OpenAI-compatible provider, create a Modal Secret
without placing credentials in Git or Vercel:

```powershell
py -m modal secret create ai-drug-design-agent-llm `
  LLM_ENABLED=true `
  LLM_BASE_URL=https://your-provider.example/v1 `
  LLM_API_KEY=replace-with-private-key `
  LLM_MODEL=your-model-name
$env:MODAL_LLM_SECRET_NAME = 'ai-drug-design-agent-llm'
```

`LLM_BASE_URL` may be an API base such as `/v1` or the complete
`/v1/chat/completions` URL. This works with OpenAI, DeepSeek, and other
OpenAI-compatible providers without vendor-specific SDK code. If
`MODAL_LLM_SECRET_NAME` is not set, deployment remains fully functional with
the rules parser. Never configure `LLM_API_KEY` as a `VITE_*` variable.

## 5. Deploy the FastAPI endpoint

This is the first step that creates the serverless GPU deployment:

```powershell
Set-Location 'E:\blog\AIProjects\drug-design-agent-public'
py -m modal deploy .\modal_app.py
```

The command prints the public HTTPS URL for `fastapi_api`, similar to:

```text
https://<workspace>--ai-drug-design-agent-fastapi-api.modal.run
```

Copy the exact URL from the deploy output:

```powershell
$ApiUrl = 'https://<workspace>--ai-drug-design-agent-fastapi-api.modal.run'
```

Use `$ApiUrl` as the backend origin in the Vercel frontend. Existing FastAPI CORS configuration permits browser access.

## 6. Test health and generation

Health only:

```powershell
curl.exe "$ApiUrl/api/health"
```

Submit a minimal generation request:

```powershell
curl.exe -X POST "$ApiUrl/api/generate" `
  -H "Content-Type: application/json" `
  -d '{"target":"ESR1","num_samples":1,"run_docking":false}'
```

Run the complete smoke test, which checks CUDA, RDKit and Vina, submits one molecule, then polls the returned task until completion:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\modal_smoke_test.ps1 `
  -BaseUrl $ApiUrl
```

To inspect a task manually:

```powershell
curl.exe "$ApiUrl/api/tasks/<TASK_ID>"
```

## Runtime notes

- `max_containers=1` keeps the existing in-memory task registry consistent without changing API logic.
- Concurrent HTTP inputs remain enabled so `/api/tasks/{task_id}` can be polled while generation runs.
- `min_containers=0` and `scaledown_window=300` allow the GPU container to scale to zero after an idle interval.
- The asset extraction Function is CPU-only. The API Function requests an A10 GPU only after deployment receives traffic.
- Keep `runpod-assets.tar.gz`, Modal credentials, `.env` files, model weights and data private.
- Existing RunPod deployment files remain valid and independent of this Modal path.
