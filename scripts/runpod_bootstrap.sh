#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/workspace/ai-drug-design-agent}"

if [ ! -f "${APP_DIR}/requirements.txt" ]; then
  APP_DIR="."
fi

cd "${APP_DIR}"

if [ ! -f .env ]; then
  cp .env.runpod.example .env
  echo "Created .env from .env.runpod.example"
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

MODEL_ROOT="${RUNPOD_MODEL_ROOT:-/workspace/models}"
DATA_ROOT="${RUNPOD_DATA_ROOT:-/workspace/data}"

missing=0

check_file() {
  if [ ! -f "$1" ]; then
    echo "Missing required RunPod asset: $1" >&2
    missing=1
  fi
}

check_file "${MODEL_ROOT}/e2po/direct_ki_e2po_15k.pt"
check_file "${MODEL_ROOT}/esm2/config.json"
check_file "${MODEL_ROOT}/esm2/pytorch_model.bin"
check_file "${MODEL_ROOT}/bert-base-uncased/config.json"
check_file "${DATA_ROOT}/targets/targets.json"

for target in ESR1 HCRTR1 JAK1 P2RX3 KDM1A IDH1 RIOK1 NR4A1 GRIK1 CCR9 FTO SPIN1; do
  check_file "${DATA_ROOT}/targets/fasta/${target}.fasta"
done

for pdb_id in 2r6w 4zjc 3eyg 5svl 5lhg 4umx 4otp 3v3q 3fv1 5lwe 4zs3 5jsj; do
  check_file "${DATA_ROOT}/structures/${pdb_id}/${pdb_id}_protein_cleaned.pdbqt"
  check_file "${DATA_ROOT}/structures/${pdb_id}/${pdb_id}_ligand.sdf"
done

if [ "${missing}" -ne 0 ]; then
  echo "Extract runpod-assets.tar.gz into /workspace before starting the API." >&2
  exit 2
fi

if ! command -v nvidia-smi >/dev/null 2>&1; then
  echo "nvidia-smi is unavailable; deploy this service on an NVIDIA GPU Pod." >&2
  exit 3
fi

nvidia-smi

if [ "${RUNPOD_SKIP_INSTALL:-0}" != "1" ]; then
  python -m pip install --upgrade pip
  python -m pip install -r requirements.txt
fi

python -c 'import torch; from rdkit import Chem; from transformers import AutoModel, AutoTokenizer; from vina import Vina; from meeko import MoleculePreparation; assert torch.cuda.is_available(), "PyTorch cannot access the NVIDIA GPU"; print(f"CUDA ready: {torch.cuda.get_device_name(0)}"); print("PyTorch, ESM-2 dependencies, RDKit, AutoDock Vina and Meeko imports: PASS")'

mkdir -p /workspace/logs

exec python -m uvicorn app.main:app \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8000}"
