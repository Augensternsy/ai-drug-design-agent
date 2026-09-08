# RunPod Readiness Report

**Status: READY FOR RUNPOD**

Local preparation is complete. Creating a paid GPU Pod and executing GPU inference were intentionally not performed because those steps require the owner's RunPod login and billing authorization.

## Prepared deployment surface

- RunPod PyTorch 2.1 / CUDA 11.8 Docker base.
- FastAPI bound to `0.0.0.0:8000`.
- Network Volume paths standardized as `/workspace/models` and `/workspace/data`.
- E2PO checkpoint fixed at `/workspace/models/e2po/direct_ki_e2po_15k.pt`.
- Sampling fixed at `sampling_steps=200` and `clamp_mode=none`.
- ESM-2, RDKit, AutoDock Vina, Meeko and FastAPI dependencies declared.
- Bootstrap and API smoke-test scripts included.
- Complete Pod/Volume/upload/clone/start/test runbook included.

## Private asset package

```text
Archive: runpod-assets.tar.gz (stored outside the Git repository)
Size: 1,028,874,701 bytes (0.958 GiB)
Entries: 46
SHA-256: 31c926aa70e03dfac4939ba1e349f14fa6cabea8ee553c00577b775f2b83d199
```

The archive contains only the required E2PO checkpoint, ESM-2 files, lightweight tokenizer/BERT configuration, 12-target metadata and the PDBQT/SDF files used by Vina. It excludes the Base checkpoint, BERT weights/exports, precomputed experiments, outputs, logs and caches.

## Completed checks

| Check | Result |
|---|---|
| Python source syntax (53 files) | PASS |
| RunPod Bash script syntax (2 files) | PASS |
| Dockerfile CUDA/PyTorch/path/port configuration | PASS |
| Fixed checkpoint, 200 sampling steps and NoClamp | PASS |
| Archive readability, allowlist and SHA-256 | PASS |
| Public repository `.env` and weight scan | PASS — none present |
| Public repository files over 50 MB | PASS — none present |
| Credential-pattern scan | PASS — none detected |
| `.gitignore` coverage for private assets | PASS |
| Private source repository write avoidance | PASS |

The existing tokenizer source emits a Python `SyntaxWarning` for a legacy regular-expression escape, but all Python files compile successfully. The model algorithm was not changed.

## Remaining owner actions

1. Sign in to RunPod and create a Network Volume.
2. Create an NVIDIA GPU Pod, attach the volume at `/workspace`, and expose `8000/http`.
3. Upload `runpod-assets.tar.gz` to the volume and extract it into `/workspace`.
4. Clone the public GitHub repository into `/workspace/ai-drug-design-agent`.
5. Copy `.env.runpod.example` to `.env`.
6. Run `bash scripts/runpod_bootstrap.sh`.
7. Run `bash scripts/runpod_smoke_test.sh http://127.0.0.1:8000`.

See `RUNPOD_DEPLOYMENT.md` for exact commands and the external RunPod proxy test.
