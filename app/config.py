"""
Drug Design Agent v2 — Central Configuration
All paths use pathlib.Path and load dynamically from .env with fallback defaults.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# ============================================================
# Project root (auto-detected from this file's location)
# ============================================================
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Load environment variables from .env file
load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False)

# ============================================================
# Core Environment Variables & Modes
# ============================================================
DEVICE_ENV = os.getenv("DEVICE", "cuda")
INFERENCE_MODE = os.getenv("INFERENCE_MODE", "local")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ============================================================
# Model & Tokenizer Paths
# ============================================================
def _resolve_path(env_key: str, default_rel: str) -> Path:
    val = os.getenv(env_key)
    if val:
        p = Path(val)
        return p if p.is_absolute() else PROJECT_ROOT / p
    return PROJECT_ROOT / default_rel

MODEL_PATH = _resolve_path("MODEL_PATH", "models/e2po/direct_ki_e2po_15k.pt")
E2PO_CHECKPOINT = _resolve_path("E2PO_CHECKPOINT", "models/e2po/direct_ki_e2po_15k.pt")
BASE_CHECKPOINT = _resolve_path("BASE_CHECKPOINT", "models/base/PLAIN_ema_0.9999_050000.pt")
ESM2_PATH = _resolve_path("ESM_MODEL_PATH", "models/esm2")
TOKENIZER_PATH = _resolve_path("TOKENIZER_PATH", "models/tokenizer/vocab.json")
BERT_CONFIG_PATH = _resolve_path("BERT_CONFIG_PATH", "models/bert-base-uncased")

# ============================================================
# Data Paths
# ============================================================
DATA_DIR = PROJECT_ROOT / "data"
TARGET_DATA_PATH = _resolve_path("TARGET_DATA_PATH", "data/target_data_eval")
STRUCTURES_DIR = _resolve_path("STRUCTURE_DATA_PATH", "data/structures")
DEMO_DATA_DIR = _resolve_path("DEMO_DATA_PATH", "demo_data")

OUTPUTS_DIR = PROJECT_ROOT / "outputs"
SMOKE_TEST_DIR = OUTPUTS_DIR / "smoke_test"

# Ensure output directories exist
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
SMOKE_TEST_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================
# Diffusion sampling config
# ============================================================
SAMPLING_STEPS = 200
TIMESTEP_SPACING = 10
BETA_SCHEDULE = "sqrt"
DIFFUSION_STEPS = 2000
CLAMP_MODE = "none"

# Model architecture
MODEL_IN_CHANNELS = 32
MODEL_HIDDEN_SIZE = 1024
MODEL_NUM_HEADS = 16
MODEL_NUM_LAYERS = 12
MODEL_CHANNELS = 128
SELF_COND = True
VOCAB_SIZE = 37
MAX_SMILES_LEN = 170
MAX_PROTEIN_LEN = 256

ESM2_INPUT_DIM = 640
ESM2_OUTPUT_DIM = 1024

# ============================================================
# Vina / Docking Config
# ============================================================
VINA_EXECUTABLE = os.getenv("VINA_PATH", "vina")
VINA_EXHAUSTIVENESS = 8
VINA_N_POSES = 1
VINA_BOX_PADDING = 10.0

# ============================================================
# Device Setup
# ============================================================
import torch
if DEVICE_ENV == "cuda" and torch.cuda.is_available():
    DEVICE = "cuda:0"
else:
    DEVICE = "cpu"
