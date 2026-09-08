"""
Model Service — 负责加载 TG-MolDiff 模型与 ESM-2 蛋白编码器并执行分子生成推理
"""

import sys
import os
import torch
import torch.nn as nn
from types import ModuleType
from pathlib import Path
from typing import List, Tuple
from functools import partial

# ── 将 source_backup 和 improved_diffusion 加入 Python 路径 ──────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_BACKUP = _PROJECT_ROOT / "source_backup"

if str(_SOURCE_BACKUP) not in sys.path:
    sys.path.insert(0, str(_SOURCE_BACKUP))
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# ── PyTorch 2.0.0 兼容补丁 ────────────────────────────────────────────────────
if not hasattr(torch, "compiler"):
    compiler = ModuleType("compiler")
    compiler.disable = lambda func=None, recursive=False: (
        func if func is not None else (lambda f: f)
    )
    torch.compiler = compiler
    sys.modules["torch.compiler"] = compiler

_orig_load_state_dict = nn.Module.load_state_dict
def _patched_load_state_dict(self, state_dict, *args, **kwargs):
    kwargs.pop("assign", None)
    return _orig_load_state_dict(self, state_dict, *args, **kwargs)
nn.Module.load_state_dict = _patched_load_state_dict
# ─────────────────────────────────────────────────────────────────────────────

from app.config import (
    MODEL_PATH, E2PO_CHECKPOINT, BASE_CHECKPOINT, ESM2_PATH, TOKENIZER_PATH,
    MODEL_IN_CHANNELS, MODEL_HIDDEN_SIZE, MODEL_NUM_HEADS,
    MODEL_NUM_LAYERS, MODEL_CHANNELS, SELF_COND,
    VOCAB_SIZE, MAX_SMILES_LEN, MAX_PROTEIN_LEN,
    ESM2_INPUT_DIM, ESM2_OUTPUT_DIM,
    SAMPLING_STEPS, TIMESTEP_SPACING, DIFFUSION_STEPS,
    CLAMP_MODE, BETA_SCHEDULE, DEVICE,
)

# ── 延迟导入（避免在 import 时就触发 GPU 操作）────────────────────────────────
_tokenizer_cls = None
_esm2_proj_cls = None
_transformer_cls = None
_spaced_diffusion_cls = None
_gd_module = None
_denoised_fn_round = None


def _lazy_imports():
    global _tokenizer_cls, _esm2_proj_cls, _transformer_cls
    global _spaced_diffusion_cls, _gd_module, _denoised_fn_round

    if _tokenizer_cls is not None:
        return

    _imp_diff_dir = _SOURCE_BACKUP / "improved_diffusion"

    import importlib
    import importlib.util

    if "improved_diffusion" not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            "improved_diffusion",
            os.path.join(_imp_diff_dir, "__init__.py"),
            submodule_search_locations=[str(_imp_diff_dir)]
        )
        pkg = importlib.util.module_from_spec(spec)
        sys.modules["improved_diffusion"] = pkg
        spec.loader.exec_module(pkg)

    from improved_diffusion import gaussian_diffusion_self_cond as _gd
    from improved_diffusion.respace_self_cond import SpacedDiffusion
    from improved_diffusion.transformer_model2_self_cond import TransformerNetModel2
    from improved_diffusion.test_util import denoised_fn_round
    from mytokenizers import ChemformerTokenizer
    from process_train_csv import ESM2ProjectionLayer

    _gd_module = _gd
    _spaced_diffusion_cls = SpacedDiffusion
    _transformer_cls = TransformerNetModel2
    _tokenizer_cls = ChemformerTokenizer
    _esm2_proj_cls = ESM2ProjectionLayer
    _denoised_fn_round = denoised_fn_round


# ── Singleton 模型状态 ────────────────────────────────────────────────────────
_loaded_models = {}
_esm_model = None
_esm_tokenizer = None
_projection_layer = None


def get_tokenizer():
    """返回 ChemformerTokenizer 实例 (singleton)."""
    _lazy_imports()
    if "tokenizer" not in _loaded_models:
        tok = _tokenizer_cls(max_len=MAX_SMILES_LEN)
        _loaded_models["tokenizer"] = tok
    return _loaded_models["tokenizer"]


def get_diffusion():
    """返回 SpacedDiffusion 实例 (singleton)."""
    _lazy_imports()
    if "diffusion" not in _loaded_models:
        gd = _gd_module
        diffusion = _spaced_diffusion_cls(
            use_timesteps=list(range(0, DIFFUSION_STEPS, TIMESTEP_SPACING)),
            betas=gd.get_named_beta_schedule(BETA_SCHEDULE, DIFFUSION_STEPS),
            model_mean_type=gd.ModelMeanType.START_X,
            model_var_type=gd.ModelVarType.FIXED_LARGE,
            loss_type=gd.LossType.E2E_MSE,
            rescale_timesteps=True,
            model_arch="transformer",
            training_mode="e2e",
        )
        _loaded_models["diffusion"] = diffusion
    return _loaded_models["diffusion"]


def load_generation_model(model_path: str = None, device: str = DEVICE) -> nn.Module:
    """加载 TG-MolDiff 去噪模型."""
    _lazy_imports()

    ckpt_path = model_path or str(MODEL_PATH)
    if not os.path.exists(ckpt_path) and os.path.exists(str(E2PO_CHECKPOINT)):
        ckpt_path = str(E2PO_CHECKPOINT)

    cache_key = f"model_{ckpt_path}_{device}"
    if cache_key in _loaded_models:
        return _loaded_models[cache_key]

    tokenizer = get_tokenizer()
    vocab_size = len(tokenizer)

    model = _transformer_cls(
        in_channels=MODEL_IN_CHANNELS,
        model_channels=MODEL_CHANNELS,
        dropout=0.1,
        use_checkpoint=False,
        config_name="bert-base-uncased",
        training_mode="e2e",
        vocab_size=vocab_size,
        experiment_mode="lm",
        logits_mode=1,
        hidden_size=MODEL_HIDDEN_SIZE,
        num_attention_heads=MODEL_NUM_HEADS,
        num_hidden_layers=MODEL_NUM_LAYERS,
        self_cond=SELF_COND,
    )

    print(f"[ModelService] Loading checkpoint: {ckpt_path}")
    checkpoint = torch.load(ckpt_path, map_location="cpu")
    model.load_state_dict(checkpoint)
    model.to(device)
    model.eval()

    n_params = sum(p.numel() for p in model.parameters())
    print(f"[ModelService] Model loaded successfully. Parameters: {n_params:,}")

    _loaded_models[cache_key] = model
    return model


def load_esm2(device: str = DEVICE):
    """加载 ESM-2 蛋白编码器."""
    _lazy_imports()

    global _esm_model, _esm_tokenizer, _projection_layer

    if _esm_model is not None:
        return _esm_model, _esm_tokenizer, _projection_layer

    from transformers import AutoModel, AutoTokenizer

    esm_path = str(ESM2_PATH)
    print(f"[ModelService] Loading ESM-2 from: {esm_path}")
    _esm_tokenizer = AutoTokenizer.from_pretrained(esm_path)
    _esm_model = AutoModel.from_pretrained(esm_path).to(device)
    _esm_model.eval()

    _projection_layer = _esm2_proj_cls(
        input_dim=ESM2_INPUT_DIM,
        output_dim=ESM2_OUTPUT_DIM,
    ).to(device)
    torch.manual_seed(42)
    for m in _projection_layer.modules():
        if isinstance(m, nn.Linear):
            nn.init.xavier_uniform_(m.weight)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
    _projection_layer.eval()

    print(f"[ModelService] ESM-2 loaded successfully.")
    return _esm_model, _esm_tokenizer, _projection_layer


def encode_protein_sequence(
    sequence: str,
    device: str = DEVICE,
) -> Tuple[torch.Tensor, torch.Tensor]:
    """将氨基酸序列编码为蛋白质条件特征."""
    esm_model, esm_tokenizer, projection_layer = load_esm2(device)

    inputs = esm_tokenizer(
        [sequence.strip().upper()],
        return_tensors="pt",
        padding=True,
        truncation=True,
        max_length=512,
    ).to(device)

    with torch.no_grad():
        outputs = esm_model(**inputs)
        token_emb = outputs.last_hidden_state
        token_emb = projection_layer(token_emb)

    attn_mask = inputs["attention_mask"]
    states = token_emb[0]
    mask = attn_mask[0]
    seq_len = states.shape[0]

    pad_len = MAX_PROTEIN_LEN - seq_len
    if pad_len > 0:
        states = torch.nn.functional.pad(states, (0, 0, 0, pad_len))
        mask = torch.nn.functional.pad(mask, (0, pad_len))
    else:
        states = states[:MAX_PROTEIN_LEN, :]
        mask = mask[:MAX_PROTEIN_LEN]

    return states.unsqueeze(0), mask.unsqueeze(0)


def sanitize_smiles(smiles: str) -> str:
    """清理和规范化生成出来的 SMILES 字符串."""
    if not smiles:
        return None
    if '[EOS]' in smiles:
        smiles = smiles.split('[EOS]')[0]
    smiles = smiles.replace('[SOS]', '').replace('[PAD]', '').strip()

    open_count = smiles.count('(')
    close_count = smiles.count(')')
    if open_count > close_count:
        smiles = smiles + ')' * (open_count - close_count)
    elif close_count > open_count:
        for _ in range(close_count - open_count):
            if ')' in smiles:
                smiles = smiles[:smiles.rfind(')')] + smiles[smiles.rfind(')')+1:]
    return smiles


def generate_molecules_for_target(
    target: str,
    num_samples: int = 3,
    device: str = DEVICE
) -> List[str]:
    """
    为指定靶点生成 candidate SMILES 列表。
    """
    _lazy_imports()
    from app.services.target_service import TargetRegistry

    model = load_generation_model(device=device)
    diffusion = get_diffusion()
    tokenizer = get_tokenizer()

    seq = TargetRegistry.get_sequence(target)
    desc_state, desc_mask = encode_protein_sequence(seq, device=device)

    # Setup clamping
    class ClampingArgs:
        clamp = "clamp"
        clamp_thresh = 350
        clamp_top_k = 5
        clamp_temp = 0.1
        clamp_soft = True

    model_emb = model.word_embedding.weight[:len(tokenizer)].clone().detach().to(device)
    denoised_fn = partial(_denoised_fn_round, ClampingArgs(), model_emb)

    batch_desc_state = desc_state.repeat(num_samples, 1, 1)
    batch_desc_mask = desc_mask.repeat(num_samples, 1)

    sample_shape = (num_samples, MAX_SMILES_LEN, model.in_channels)

    with torch.no_grad():
        samples = diffusion.p_sample_loop(
            model,
            sample_shape,
            clip_denoised=False,
            model_kwargs={},
            progress=False,
            desc=(batch_desc_state, batch_desc_mask),
            denoised_fn=denoised_fn
        )

        logits = model.get_logits(samples)
        logits = logits[..., :len(tokenizer)]
        cands = torch.topk(logits, k=1, dim=-1)
        token_ids = cands.indices.squeeze(-1)

        raw_smiles = tokenizer.decode(token_ids)

    cleaned_smiles = []
    for smi in raw_smiles:
        clean = sanitize_smiles(smi)
        if clean:
            cleaned_smiles.append(clean)
        else:
            cleaned_smiles.append("INVALID")

    return cleaned_smiles
