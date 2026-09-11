"""Modal Serverless GPU entrypoint for the existing FastAPI application.

The model and data stay in a named Modal Volume mounted at /workspace.  This
module only supplies infrastructure configuration; inference and API behavior
remain in app/.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tarfile
from pathlib import Path

import modal


APP_NAME = os.getenv("MODAL_APP_NAME", "ai-drug-design-agent")
VOLUME_NAME = os.getenv("MODAL_VOLUME_NAME", "ai-drug-design-assets")
GPU_TYPE = os.getenv("MODAL_GPU", "A10")
SCALEDOWN_WINDOW = int(os.getenv("MODAL_SCALEDOWN_WINDOW", "300"))

PROJECT_DIR = "/root/drug-design-agent"
VOLUME_MOUNT = "/workspace"
ASSET_ARCHIVE = Path(VOLUME_MOUNT) / "runpod-assets.tar.gz"
ASSET_SHA256 = "31c926aa70e03dfac4939ba1e349f14fa6cabea8ee553c00577b775f2b83d199"

LOCAL_ROOT = Path(__file__).resolve().parent

app = modal.App(APP_NAME)
assets_volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=False)
llm_secret = modal.Secret.from_name("ai-drug-design-agent-llm")

runtime_env = {
    "PYTHONUNBUFFERED": "1",
    "PYTHONPATH": PROJECT_DIR,
    "DEVICE": "cuda",
    "INFERENCE_MODE": "local",
    "MODEL_PATH": "/workspace/models/e2po/direct_ki_e2po_15k.pt",
    "E2PO_CHECKPOINT": "/workspace/models/e2po/direct_ki_e2po_15k.pt",
    "ESM_MODEL_PATH": "/workspace/models/esm2",
    "TOKENIZER_PATH": "/workspace/models/tokenizer",
    "BERT_CONFIG_PATH": "/workspace/models/bert-base-uncased",
    "TARGET_DATA_PATH": "/workspace/data/targets/fasta",
    "STRUCTURE_DATA_PATH": "/workspace/data/structures",
    "DEMO_DATA_PATH": "/workspace/data/demo",
    "VINA_PATH": "vina",
    "HOST": "0.0.0.0",
    "PORT": "8000",
    "MAX_NUM_SAMPLES": "5",
    "REQUEST_COOLDOWN_SECONDS": "15",
}

runtime_image = (
    modal.Image.from_registry(
        "nvidia/cuda:12.4.1-runtime-ubuntu22.04",
        add_python="3.10",
    )
    .entrypoint([])
    .apt_install("git", "libxext6", "libxrender1", "libglib2.0-0")
    .pip_install_from_requirements(str(LOCAL_ROOT / "requirements.txt"))
    .env(runtime_env)
    .workdir(PROJECT_DIR)
    .add_local_dir(str(LOCAL_ROOT / "app"), remote_path=f"{PROJECT_DIR}/app")
    .add_local_dir(
        str(LOCAL_ROOT / "source_backup"),
        remote_path=f"{PROJECT_DIR}/source_backup",
    )
)

asset_image = modal.Image.debian_slim(python_version="3.10")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_extract(archive: tarfile.TarFile, destination: Path) -> None:
    """Extract a tar archive after rejecting links and path traversal."""
    destination = destination.resolve()
    for member in archive.getmembers():
        if member.issym() or member.islnk():
            raise ValueError(f"Archive links are not allowed: {member.name}")
        if not (member.isfile() or member.isdir()):
            raise ValueError(f"Unsupported archive entry: {member.name}")
        target = (destination / member.name).resolve()
        if target != destination and destination not in target.parents:
            raise ValueError(f"Unsafe archive path: {member.name}")
    archive.extractall(destination)


@app.function(
    image=asset_image,
    volumes={VOLUME_MOUNT: assets_volume},
    timeout=3600,
)
def extract_assets() -> dict[str, str]:
    """Verify and extract the private asset bundle into the Modal Volume."""
    if not ASSET_ARCHIVE.is_file():
        raise FileNotFoundError(f"Asset archive not found: {ASSET_ARCHIVE}")

    actual_sha256 = _sha256(ASSET_ARCHIVE)
    if actual_sha256 != ASSET_SHA256:
        raise ValueError(
            f"Asset SHA-256 mismatch: expected {ASSET_SHA256}, got {actual_sha256}"
        )

    with tarfile.open(ASSET_ARCHIVE, mode="r:gz") as archive:
        _safe_extract(archive, Path(VOLUME_MOUNT))

    target_to_pdb = {
        "ESR1": "2r6w",
        "HCRTR1": "4zjc",
        "JAK1": "3eyg",
        "P2RX3": "5svl",
        "KDM1A": "5lhg",
        "IDH1": "4umx",
        "RIOK1": "4otp",
        "NR4A1": "3v3q",
        "GRIK1": "3fv1",
        "CCR9": "5lwe",
        "FTO": "4zs3",
        "SPIN1": "5jsj",
    }
    required = [
        Path("/workspace/models/e2po/direct_ki_e2po_15k.pt"),
        Path("/workspace/models/esm2/pytorch_model.bin"),
        Path("/workspace/models/bert-base-uncased/config.json"),
        Path("/workspace/models/tokenizer/mytokenizers.py"),
        Path("/workspace/data/targets/targets.json"),
        Path("/workspace/data/targets/test_target_sequences.csv"),
    ]
    for target, pdb_id in target_to_pdb.items():
        required.extend(
            (
                Path(f"/workspace/data/targets/fasta/{target}.fasta"),
                Path(
                    f"/workspace/data/structures/{pdb_id}/"
                    f"{pdb_id}_protein_cleaned.pdbqt"
                ),
                Path(
                    f"/workspace/data/structures/{pdb_id}/"
                    f"{pdb_id}_ligand.sdf"
                ),
            )
        )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required extracted assets: " + ", ".join(missing))

    assets_volume.commit()
    return {
        "status": "ok",
        "sha256": actual_sha256,
        "volume": VOLUME_NAME,
        "mount": VOLUME_MOUNT,
    }


@app.function(
    image=runtime_image,
    gpu=GPU_TYPE,
    volumes={VOLUME_MOUNT: assets_volume},
    min_containers=0,
    max_containers=1,
    scaledown_window=SCALEDOWN_WINDOW,
    timeout=3600,
    secrets=[llm_secret],
)
@modal.concurrent(max_inputs=8)
@modal.asgi_app()
def fastapi_api():
    """Expose the existing FastAPI app as a Modal HTTP endpoint."""
    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)
    from app.main import app as fastapi_app

    return fastapi_app
