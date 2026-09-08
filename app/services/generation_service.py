"""
Generation Service — 负责完整的分子生成流程

Pipeline:
  protein_sequence
    → ESM-2 embedding
    → ESM2ProjectionLayer (640→1024)
    → TG-MolDiff diffusion sampling (200 steps, NoClamp)
    → SMILES decoding (ChemformerTokenizer)
    → sanitize & RDKit validity check
    → return [{"smiles": ..., "valid": ...}]
"""

import torch
import numpy as np
import csv
import os
from functools import partial

from app.config import (
    DEVICE, DEFAULT_NUM_SAMPLES, DEFAULT_BATCH_SIZE,
    DEFAULT_MODEL, MAX_SMILES_LEN, RANDOM_SEED, CLAMP_MODE,
    SMOKE_TEST_DIR,
)


def sanitize_smiles(smiles: str) -> str | None:
    """清理 SMILES：截断 EOS、移除特殊 token、修复不平衡括号。"""
    if not smiles:
        return None
    if "[EOS]" in smiles:
        smiles = smiles.split("[EOS]")[0]
    smiles = smiles.replace("[SOS]", "").replace("[PAD]", "").strip()
    open_count = smiles.count("(")
    close_count = smiles.count(")")
    if open_count > close_count:
        smiles = smiles + ")" * (open_count - close_count)
    elif close_count > open_count:
        for _ in range(close_count - open_count):
            if ")" in smiles:
                smiles = smiles[: smiles.rfind(")")] + smiles[smiles.rfind(")") + 1 :]
    return smiles if smiles else None


def is_valid_smiles(smiles: str) -> bool:
    """RDKit validity check."""
    if not smiles:
        return False
    try:
        from rdkit import Chem
        mol = Chem.MolFromSmiles(smiles)
        return mol is not None
    except Exception:
        return False


def generate_molecules(
    protein_sequence: str | None = None,
    target: str | None = None,
    num_samples: int = DEFAULT_NUM_SAMPLES,
    batch_size: int = DEFAULT_BATCH_SIZE,
    model_name: str = DEFAULT_MODEL,
    sampling_steps: int | None = None,
    device: str = DEVICE,
    seed: int = RANDOM_SEED,
) -> list[dict]:
    """
    生成候选分子。

    Args:
        protein_sequence: 氨基酸序列字符串（优先使用）
        target: 靶点名称（如 "ESR1"），若 protein_sequence 为 None 则从 FASTA 读取
        num_samples: 生成分子数量
        batch_size: 每次推理的批次大小
        model_name: "e2po"（默认，DLPS-E2PO-v3-15k）或 "base"（PathB-50k）
        sampling_steps: 扩散步数，默认 200
        device: 运行设备
        seed: 随机种子

    Returns:
        list of {"smiles": str, "valid": bool}
    """
    from app.services.model_service import (
        load_generation_model,
        load_esm2,
        encode_protein_sequence,
        get_tokenizer,
        get_diffusion,
    )

    torch.manual_seed(seed)
    np.random.seed(seed)

    # ── 获取蛋白质序列 ─────────────────────────────────────────────────────
    if protein_sequence is None:
        if target is None:
            raise ValueError("必须提供 protein_sequence 或 target")
        from app.config import FASTA_DIR
        fasta_path = os.path.join(FASTA_DIR, f"{target}.fasta")
        if not os.path.exists(fasta_path):
            raise FileNotFoundError(f"FASTA 文件不存在: {fasta_path}")
        with open(fasta_path, "r") as f:
            lines = f.readlines()
        protein_sequence = "".join(
            line.strip() for line in lines if not line.startswith(">")
        )

    # ── 加载组件 ──────────────────────────────────────────────────────────
    print(f"[GenerationService] Loading model: {model_name}")
    model = load_generation_model(model_name, device)
    esm_model, esm_tokenizer, projection_layer = load_esm2(device)
    tokenizer = get_tokenizer()
    diffusion = get_diffusion()

    # ── 编码蛋白质 ────────────────────────────────────────────────────────
    print(f"[GenerationService] Encoding protein sequence (len={len(protein_sequence)})...")
    desc_state, desc_mask = encode_protein_sequence(
        protein_sequence, esm_model, esm_tokenizer, projection_layer, device
    )

    # ── 扩散采样 ──────────────────────────────────────────────────────────
    # 当 clamp_mode = 'none'（论文主结果），denoised_fn = None
    denoised_fn = None
    if CLAMP_MODE == "clamp":
        from improved_diffusion.test_util import denoised_fn_round
        import argparse
        _args = argparse.Namespace(
            clamp="clamp",
            clamp_thresh=350,
            clamp_top_k=5,
            clamp_temp=0.1,
            clamp_soft=True,
        )
        model_emb = model.word_embedding.weight[:len(tokenizer)].clone().detach().to(device)
        denoised_fn = partial(denoised_fn_round, _args, model_emb)

    all_samples = []
    num_done = 0
    model.eval()

    print(f"[GenerationService] Generating {num_samples} samples...")
    while num_done < num_samples:
        current_batch = min(batch_size, num_samples - num_done)
        b_desc_state = desc_state.repeat(current_batch, 1, 1)
        b_desc_mask = desc_mask.repeat(current_batch, 1)
        sample_shape = (current_batch, MAX_SMILES_LEN, model.in_channels)

        with torch.no_grad():
            samples = diffusion.p_sample_loop(
                model,
                sample_shape,
                clip_denoised=False,
                model_kwargs={},
                progress=True,
                desc=(b_desc_state, b_desc_mask),
                denoised_fn=denoised_fn,
            )
        all_samples.append(samples)
        num_done += current_batch
        print(f"  [{num_done}/{num_samples}] done")

    all_samples = torch.cat(all_samples, dim=0).to(device)

    # ── 解码 SMILES ───────────────────────────────────────────────────────
    print("[GenerationService] Decoding SMILES...")
    with torch.no_grad():
        logits = model.get_logits(all_samples)
        logits = logits[..., : len(tokenizer)]
        token_ids = torch.argmax(logits, dim=-1)

    results = []
    for i in range(token_ids.shape[0]):
        raw = tokenizer.decode_one(token_ids[i])
        clean = sanitize_smiles(raw)
        valid = is_valid_smiles(clean)
        results.append({"smiles": clean or "INVALID", "valid": valid})

    valid_count = sum(1 for r in results if r["valid"])
    print(
        f"[GenerationService] Done. "
        f"Valid: {valid_count}/{num_samples} ({valid_count/num_samples*100:.1f}%)"
    )
    return results


def generate_and_save(
    target: str,
    num_samples: int = DEFAULT_NUM_SAMPLES,
    model_name: str = DEFAULT_MODEL,
    output_path: str | None = None,
    device: str = DEVICE,
) -> str:
    """
    生成分子并保存到 CSV。返回保存路径。
    """
    results = generate_molecules(
        target=target,
        num_samples=num_samples,
        model_name=model_name,
        device=device,
    )

    if output_path is None:
        os.makedirs(SMOKE_TEST_DIR, exist_ok=True)
        output_path = os.path.join(SMOKE_TEST_DIR, f"{target}_generated.csv")

    with open(output_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["SMILES", "Valid"])
        for r in results:
            writer.writerow([r["smiles"], r["valid"]])

    print(f"[GenerationService] Results saved to: {output_path}")
    return output_path
