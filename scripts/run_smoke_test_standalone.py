#!/usr/bin/env python
"""
Drug Design Agent v2 — ESR1 Generation Smoke Test (Standalone)

这个脚本是独立的 Smoke Test，无需依赖 app/ 包结构，
直接从 source_backup 加载所有推理组件。

Usage:
  /home/zmx/wsy/env/tgm-dlm/bin/python -s scripts/run_smoke_test_standalone.py
"""

import sys
import os
import csv
import time
import torch
import torch.nn as nn
from types import ModuleType

# ══════════════════════════════════════════════════════════════════════════════
# Step 0: PyTorch 兼容补丁 (必须最先执行!)
# ══════════════════════════════════════════════════════════════════════════════
if not hasattr(torch, "compiler"):
    compiler = ModuleType("compiler")
    compiler.disable = lambda func=None, recursive=False: (
        func if func is not None else (lambda f: f)
    )
    torch.compiler = compiler
    sys.modules["torch.compiler"] = compiler

orig_load_state_dict = nn.Module.load_state_dict
def patched_load_state_dict(self, state_dict, *args, **kwargs):
    kwargs.pop("assign", None)
    return orig_load_state_dict(self, state_dict, *args, **kwargs)
nn.Module.load_state_dict = patched_load_state_dict

print("[Patch] torch.compiler + load_state_dict: OK")

# ══════════════════════════════════════════════════════════════════════════════
# Step 1: 路径配置
# ══════════════════════════════════════════════════════════════════════════════
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
SOURCE_BACKUP = os.path.join(PROJECT_ROOT, "source_backup")
IMP_DIFF_DIR = os.path.join(SOURCE_BACKUP, "improved_diffusion")

sys.path.insert(0, SOURCE_BACKUP)

# Config (inline, no app.config import)
E2PO_CHECKPOINT = os.path.join(PROJECT_ROOT, "models", "e2po", "direct_ki_e2po_15k.pt")
BASE_CHECKPOINT = os.path.join(PROJECT_ROOT, "models", "base", "PLAIN_ema_0.9999_050000.pt")
ESM2_PATH = os.path.join(PROJECT_ROOT, "models", "esm2")
FASTA_DIR = os.path.join(PROJECT_ROOT, "data", "targets", "fasta")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs", "smoke_test")
TARGET = "ESR1"
NUM_SAMPLES = 3
BATCH_SIZE = 3
SAMPLING_STEPS = 200
TIMESTEP_SPACING = 10
DIFFUSION_STEPS = 2000

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
print(f"[Config] Device: {device}")
print(f"[Config] E2PO checkpoint: {E2PO_CHECKPOINT}")
print(f"[Config] ESM-2: {ESM2_PATH}")
print(f"[Config] Target: {TARGET}")
print(f"[Config] Samples: {NUM_SAMPLES}, Steps: {SAMPLING_STEPS}")

# ══════════════════════════════════════════════════════════════════════════════
# Step 2: 注册 improved_diffusion 包
# ══════════════════════════════════════════════════════════════════════════════
import importlib.util

spec = importlib.util.spec_from_file_location(
    "improved_diffusion",
    os.path.join(IMP_DIFF_DIR, "__init__.py"),
    submodule_search_locations=[IMP_DIFF_DIR],
)
pkg = importlib.util.module_from_spec(spec)
sys.modules["improved_diffusion"] = pkg
spec.loader.exec_module(pkg)
print("[Step 2] improved_diffusion package registered")

# ══════════════════════════════════════════════════════════════════════════════
# Step 3: 导入模型组件
# ══════════════════════════════════════════════════════════════════════════════
from improved_diffusion import gaussian_diffusion_self_cond as gd
from improved_diffusion.respace_self_cond import SpacedDiffusion
from improved_diffusion.transformer_model2_self_cond import TransformerNetModel2
from mytokenizers import ChemformerTokenizer
from process_train_csv import ESM2ProjectionLayer
from transformers import AutoModel, AutoTokenizer
print("[Step 3] All model imports OK")

# ══════════════════════════════════════════════════════════════════════════════
# Step 4: 初始化 Tokenizer 和 Diffusion
# ══════════════════════════════════════════════════════════════════════════════
tokenizer = ChemformerTokenizer(max_len=170)
vocab_size = len(tokenizer)
print(f"[Step 4] Tokenizer vocab_size: {vocab_size}")

diffusion = SpacedDiffusion(
    use_timesteps=list(range(0, DIFFUSION_STEPS, TIMESTEP_SPACING)),
    betas=gd.get_named_beta_schedule("sqrt", DIFFUSION_STEPS),
    model_mean_type=gd.ModelMeanType.START_X,
    model_var_type=gd.ModelVarType.FIXED_LARGE,
    loss_type=gd.LossType.E2E_MSE,
    rescale_timesteps=True,
    model_arch="transformer",
    training_mode="e2e",
)
print(f"[Step 4] SpacedDiffusion: {len(diffusion.timestep_map)} steps")

# ══════════════════════════════════════════════════════════════════════════════
# Step 5: 加载 TG-MolDiff 模型（E2PO checkpoint）
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[Step 5] Loading model from: {E2PO_CHECKPOINT}")
model = TransformerNetModel2(
    in_channels=32, model_channels=128, dropout=0.1, use_checkpoint=False,
    config_name="bert-base-uncased", training_mode="e2e", vocab_size=vocab_size,
    experiment_mode="lm", logits_mode=1, hidden_size=1024, num_attention_heads=16,
    num_hidden_layers=12, self_cond=True,
)
t_load = time.time()
ckpt = torch.load(E2PO_CHECKPOINT, map_location="cpu")
model.load_state_dict(ckpt)
model.to(device)
model.eval()
n_params = sum(p.numel() for p in model.parameters())
print(f"[Step 5] Checkpoint loaded in {time.time()-t_load:.1f}s. Params: {n_params:,}")

# ══════════════════════════════════════════════════════════════════════════════
# Step 6: 加载 ESM-2
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[Step 6] Loading ESM-2 from: {ESM2_PATH}")
esm_tokenizer = AutoTokenizer.from_pretrained(ESM2_PATH)
esm_model = AutoModel.from_pretrained(ESM2_PATH).to(device)
esm_model.eval()

projection_layer = ESM2ProjectionLayer(input_dim=640, output_dim=1024).to(device)
torch.manual_seed(42)
for m in projection_layer.modules():
    if isinstance(m, nn.Linear):
        nn.init.xavier_uniform_(m.weight)
        if m.bias is not None:
            nn.init.zeros_(m.bias)
projection_layer.eval()
print(f"[Step 6] ESM-2 loaded OK")

# ══════════════════════════════════════════════════════════════════════════════
# Step 7: 读取 ESR1 序列并编码
# ══════════════════════════════════════════════════════════════════════════════
fasta_path = os.path.join(FASTA_DIR, f"{TARGET}.fasta")
with open(fasta_path, "r") as f:
    lines = f.readlines()
seq = "".join(line.strip() for line in lines if not line.startswith(">"))
print(f"\n[Step 7] {TARGET} sequence length: {len(seq)}")

inputs = esm_tokenizer(
    [seq.strip().upper()], return_tensors="pt", padding=True,
    truncation=True, max_length=512
).to(device)

with torch.no_grad():
    outputs = esm_model(**inputs)
    token_emb = outputs.last_hidden_state
    token_emb = projection_layer(token_emb)

attn_mask = inputs["attention_mask"]
states = token_emb[0]
mask = attn_mask[0]
seq_len = states.shape[0]
pad_len = 256 - seq_len
if pad_len > 0:
    states = torch.nn.functional.pad(states, (0, 0, 0, pad_len))
    mask = torch.nn.functional.pad(mask, (0, pad_len))
else:
    states = states[:256, :]
    mask = mask[:256]
desc_state = states.unsqueeze(0)
desc_mask = mask.unsqueeze(0)
print(f"[Step 7] Protein embedding: {desc_state.shape}")

# ══════════════════════════════════════════════════════════════════════════════
# Step 8: Diffusion Sampling
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[Step 8] Diffusion sampling {NUM_SAMPLES} molecules (200 steps, NoClamp)...")
t_sample = time.time()
b_desc_state = desc_state.repeat(NUM_SAMPLES, 1, 1)
b_desc_mask = desc_mask.repeat(NUM_SAMPLES, 1)
sample_shape = (NUM_SAMPLES, 170, model.in_channels)

with torch.no_grad():
    samples = diffusion.p_sample_loop(
        model, sample_shape,
        clip_denoised=False,
        model_kwargs={},
        progress=True,
        desc=(b_desc_state, b_desc_mask),
        denoised_fn=None,  # NoClamp
    )

print(f"[Step 8] Sampling done in {time.time()-t_sample:.1f}s. Shape: {samples.shape}")

# ══════════════════════════════════════════════════════════════════════════════
# Step 9: Decode SMILES
# ══════════════════════════════════════════════════════════════════════════════
print("\n[Step 9] Decoding SMILES...")
with torch.no_grad():
    logits = model.get_logits(samples)
    logits = logits[..., :vocab_size]
    token_ids = torch.argmax(logits, dim=-1)

def sanitize(smi):
    if not smi: return None
    if "[EOS]" in smi: smi = smi.split("[EOS]")[0]
    smi = smi.replace("[SOS]", "").replace("[PAD]", "").strip()
    open_c = smi.count("(")
    close_c = smi.count(")")
    if open_c > close_c:
        smi += ")" * (open_c - close_c)
    elif close_c > open_c:
        for _ in range(close_c - open_c):
            if ")" in smi:
                smi = smi[:smi.rfind(")")] + smi[smi.rfind(")")+1:]
    return smi if smi else None

results = []
for i in range(token_ids.shape[0]):
    raw = tokenizer.decode_one(token_ids[i])
    clean = sanitize(raw)
    valid = False
    if clean:
        try:
            from rdkit import Chem
            mol = Chem.MolFromSmiles(clean)
            valid = mol is not None
        except:
            pass
    results.append({"smiles": clean or "INVALID", "valid": valid})

# ══════════════════════════════════════════════════════════════════════════════
# Step 10: RDKit 性质评价
# ══════════════════════════════════════════════════════════════════════════════
from rdkit import Chem
from rdkit.Chem import QED, Descriptors, rdMolDescriptors

print("\n[Step 10] RDKit property evaluation:")
props_results = []
for r in results:
    if r["valid"]:
        mol = Chem.MolFromSmiles(r["smiles"])
        if mol:
            qed = QED.default(mol)
            mw = Descriptors.MolWt(mol)
            logp = Descriptors.MolLogP(mol)
            hbd = rdMolDescriptors.CalcNumHBD(mol)
            hba = rdMolDescriptors.CalcNumHBA(mol)
            ro5 = bool(mw <= 500 and logp <= 5 and hbd <= 5 and hba <= 10)
            sa_val = None
            try:
                from rdkit.Contrib.SA_Score import sascorer
                sa_val = sascorer.calculateScore(mol)
            except:
                pass
            props_results.append({
                "smiles": r["smiles"], "valid": True,
                "qed": qed, "sa": sa_val, "mol_wt": mw,
                "log_p": logp, "ro5": ro5
            })
            print(f"  ✓ {r['smiles'][:50]}")
            print(f"    QED={qed:.3f}, MolWt={mw:.1f}, LogP={logp:.2f}, Ro5={ro5}")
            if sa_val: print(f"    SA={sa_val:.2f}")
    else:
        print(f"  ✗ INVALID: {r['smiles'][:50]}")

# ══════════════════════════════════════════════════════════════════════════════
# Step 11: 保存结果
# ══════════════════════════════════════════════════════════════════════════════
os.makedirs(OUTPUT_DIR, exist_ok=True)
output_csv = os.path.join(OUTPUT_DIR, f"{TARGET}_generated.csv")

with open(output_csv, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["SMILES", "Valid", "QED", "SA", "MolWt", "LogP", "Ro5"])
    for r in results:
        if r["valid"]:
            p = next((x for x in props_results if x["smiles"] == r["smiles"]), {})
            writer.writerow([
                r["smiles"], r["valid"],
                p.get("qed", ""), p.get("sa", ""),
                p.get("mol_wt", ""), p.get("log_p", ""), p.get("ro5", "")
            ])
        else:
            writer.writerow([r["smiles"], False, "", "", "", "", ""])

valid_count = sum(1 for r in results if r["valid"])
print(f"\n{'='*60}")
print("SMOKE TEST COMPLETE")
print(f"{'='*60}")
print(f"Total generated:  {NUM_SAMPLES}")
print(f"Valid SMILES:     {valid_count} / {NUM_SAMPLES}")
print(f"Output saved to:  {output_csv}")
print(f"{'='*60}")

if valid_count > 0:
    print(f"\n✅ SMOKE TEST PASSED!")
    sys.exit(0)
else:
    print(f"\n⚠️  SMOKE TEST: No valid molecules generated")
    sys.exit(1)
