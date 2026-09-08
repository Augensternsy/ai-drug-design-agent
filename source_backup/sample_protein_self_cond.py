# ====================================================================================
# 文件作用:
#   使用 ESM-2 和训练好的 170 长度自条件化 (Self-Conditioning) 误差自修正模型生成配体 SMILES 分子。
#
# 参照原文件:
#   scripts/sample_protein_v513.py
#
# 所做的修改与目的:
#   1. 修改导入模块：
#      - gd 导入自 improved_diffusion.gaussian_diffusion_self_cond
#      - SpacedDiffusion 导入自 improved_diffusion.respace_self_cond
#      - TransformerNetModel2 导入自 improved_diffusion.transformer_model2_self_cond
#   2. 在初始化 TransformerNetModel2 时传递 self_cond=args.self_cond 参数，激活输入端拼接。
#   3. 新增命令行与解析器参数 self_cond=True。
#   4. 默认 checkpoints 路径调整为自条件化路径 checkpoints_protein_170_self_cond/。
# ====================================================================================

import sys
import argparse
import os
import json
import numpy as np
import torch
import torch as th
import torch.nn as nn

# 1. Monkey-patch torch.compiler to support PyTorch 2.0.0 in transformers library
if not hasattr(torch, 'compiler'):
    from types import ModuleType
    compiler = ModuleType("compiler")
    compiler.disable = lambda func=None, recursive=False: (func if func is not None else (lambda f: f))
    torch.compiler = compiler
    sys.modules["torch.compiler"] = compiler

# 2. Monkey-patch nn.Module.load_state_dict to drop 'assign' keyword parameter for PyTorch 2.0.0 compatibility
orig_load_state_dict = nn.Module.load_state_dict
def patched_load_state_dict(self, state_dict, *args, **kwargs):
    kwargs.pop('assign', None)
    return orig_load_state_dict(self, state_dict, *args, **kwargs)
nn.Module.load_state_dict = patched_load_state_dict

from rdkit import Chem
from transformers import set_seed
from improved_diffusion import gaussian_diffusion_self_cond as gd
from improved_diffusion.respace_self_cond import SpacedDiffusion
from improved_diffusion.transformer_model2_self_cond import TransformerNetModel2
from mytokenizers import ChemformerTokenizer
from process_train_csv import ESM2ProjectionLayer
import csv
from improved_diffusion.test_util import denoised_fn_round
from functools import partial

def sanitize_smiles(smiles):
    """清理和修复 SMILES 字符串的正确姿势（参考 sample_protein_v3.py）"""
    if not smiles:
        return None

    # 1. 在第一个 [EOS] 处截断
    if '[EOS]' in smiles:
        smiles = smiles.split('[EOS]')[0]
        
    # 2. 移除起始符和填充符
    smiles = smiles.replace('[SOS]', '').replace('[PAD]', '').strip()

    # 尝试修复不匹配的括号
    open_count = smiles.count('(')
    close_count = smiles.count(')')
    if open_count > close_count:
        smiles = smiles + ')' * (open_count - close_count)
    elif close_count > open_count:
        for _ in range(close_count - open_count):
            if ')' in smiles:
                smiles = smiles[:smiles.rfind(')')] + smiles[smiles.rfind(')')+1:]

    return smiles

def is_valid_smiles(smiles):
    """Check if SMILES is valid."""
    if not smiles:
        return False
    mol = Chem.MolFromSmiles(smiles)
    return mol is not None

def parse_fasta(fpath):
    """Read fasta file and return sequence."""
    with open(fpath, 'r') as f:
        lines = f.readlines()
    seq = ''.join([line.strip() for line in lines if not line.startswith('>')])
    return seq

def main():
    set_seed(121)
    args = create_argparser().parse_args()

    print(f"Loading diffusion model from: {args.model_path}")
    print(f"Generating {args.num_samples} samples per protein...")
    print(f"Using DDIM: {args.use_ddim}")
    print(f"Timestep spacing: {args.timestep_spacing} (total steps: {2000 // args.timestep_spacing})")
    print(f"Clamping mode: {args.clamp}")
    print(f"Soft-Clamping settings: Thresh={args.clamp_thresh}, Top-K={args.clamp_top_k}, Temp={args.clamp_temp}, Soft={args.clamp_soft}")
    print(f"Self-Conditioning mode: {args.self_cond}")

    # 创建 ChemformerTokenizer (170 max length)
    tokenizer = ChemformerTokenizer(max_len=170)
    print(f"Tokenizer vocab size: {len(tokenizer)}")

    # 创建模型（参数与训练时保持一致，词表置为 37，激活 self_cond）
    model = TransformerNetModel2(
        in_channels=32,
        model_channels=128,
        dropout=0.1,
        use_checkpoint=False,
        config_name='bert-base-uncased',
        training_mode='e2e',
        vocab_size=len(tokenizer),
        experiment_mode='lm',
        logits_mode=1,
        hidden_size=1024,
        num_attention_heads=16,
        num_hidden_layers=12,
        self_cond=args.self_cond
    )

    # 创建扩散模型
    diffusion = SpacedDiffusion(
        use_timesteps=[i for i in range(0, 2000, args.timestep_spacing)],
        betas=gd.get_named_beta_schedule('sqrt', 2000),
        model_mean_type=gd.ModelMeanType.START_X,
        model_var_type=gd.ModelVarType.FIXED_LARGE,
        loss_type=gd.LossType.E2E_MSE,
        rescale_timesteps=True,
        model_arch='transformer',
        training_mode='e2e',
    )

    # 加载模型权重
    print(f"Loading checkpoint: {args.model_path}")
    checkpoint = th.load(args.model_path, map_location='cpu')
    model.load_state_dict(checkpoint)
    print("Checkpoint loaded successfully!")

    pytorch_total_params = sum(p.numel() for p in model.parameters())
    print(f'Model parameter count: {pytorch_total_params}')

    # 将模型移动到 GPU
    device = th.device("cuda:0" if th.cuda.is_available() else "cpu")
    print(f"Using device: {device}")
    model.to(device)
    model.eval()

    # 初始化 Clamping 权重与纠偏函数
    print("Initializing clamping weights...")
    model_emb = model.word_embedding.weight[:len(tokenizer)].clone().detach().to(device)
    denoised_fn = partial(denoised_fn_round, args, model_emb)

    # 提取特征阶段
    raw_embeddings_file = os.path.join(args.output_dir, "esm_raw_embeddings.pt")
    if not os.path.exists(raw_embeddings_file):
        print(f"\n[INFO] Raw ESM-2 embeddings not found. Extracting using extract_esm.py subprocess...")
        import subprocess
        cmd = [
            sys.executable,
            "-s",
            "extract_esm.py",
            "--fasta_dir", args.fasta_dir,
            "--esm2_path", args.esm2_path,
            "--output_file", raw_embeddings_file
        ]
        env = os.environ.copy()
        result = subprocess.run(cmd, env=env)
        if result.returncode != 0:
            raise RuntimeError(f"ESM-2 embedding extraction failed with exit code {result.returncode}")
            
    print(f"\nLoading raw ESM-2 embeddings from: {raw_embeddings_file}")
    raw_embeddings = th.load(raw_embeddings_file, map_location='cpu')

    # 初始化 ESM2ProjectionLayer 并设置确定性权重，输出蛋白质维度上限为 256
    projection_layer = ESM2ProjectionLayer(input_dim=640, output_dim=1024).to(device)
    if args.projection_weights_path and os.path.exists(args.projection_weights_path):
        print(f"Loading projection weights from: {args.projection_weights_path}")
        projection_layer.load_state_dict(th.load(args.projection_weights_path, map_location=device))
    else:
        print("[WARNING] No projection weights path provided. Initializing projection weights with seed 42.")
        th.manual_seed(42)
        for m in projection_layer.modules():
            if isinstance(m, nn.Linear):
                nn.init.xavier_uniform_(m.weight)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
    projection_layer.eval()

    name_order = ['ESR1', 'HCRTR1', 'JAK1', 'P2RX3', 'KDM1A', 'IDH1', 'RIOK1', 'NR4A1', 'GRIK1', 'CCR9', 'FTO', 'SPIN1']
    if args.target_protein.lower() != 'all':
        targets = [args.target_protein]
    else:
        targets = name_order

    for target in targets:
        csv_path = os.path.join(args.output_dir, f"generated_{target}.csv")
        if os.path.exists(csv_path):
            print(f"【跳过】靶标 {target} 的生成文件已存在，无需重复生成: {csv_path}")
            continue
        print(f"\n==================== 开始为靶标 {target} 生成分子 ====================")
        if target not in raw_embeddings:
            print(f"【错误】未在 raw_embeddings 中找到靶标 {target}，跳过...")
            continue
            
        states = raw_embeddings[target]['states'].to(device)
        mask = raw_embeddings[target]['mask'].to(device)
        
        with th.no_grad():
            states = projection_layer(states.unsqueeze(0))
            mask = mask.unsqueeze(0)
            
        pad_len = 256 - states.shape[1]
        if pad_len > 0:
            states = th.nn.functional.pad(states, (0, 0, 0, pad_len))
            mask = th.nn.functional.pad(mask, (0, pad_len))
        elif pad_len < 0:
            states = states[:, :256, :]
            mask = mask[:, :256]
            
        desc_state = states
        desc_mask = mask
        
        print(f"开始生成 {args.num_samples} 个分子...")
        all_samples = []
        num_done = 0
        
        while num_done < args.num_samples:
            batch_end = min(num_done + args.batch_size, args.num_samples)
            current_batch_size = batch_end - num_done
            
            print(f"正在生成批次 {num_done}:{batch_end} (批次大小={current_batch_size})")
            
            batch_desc_state = desc_state.repeat(current_batch_size, 1, 1)
            batch_desc_mask = desc_mask.repeat(current_batch_size, 1)
            
            sample_fn = diffusion.p_sample_loop if not args.use_ddim else diffusion.ddim_sample_loop
            sample_shape = (current_batch_size, 170, model.in_channels)  # 配体长度限制为 170
            
            with th.no_grad():
                samples = sample_fn(
                    model,
                    sample_shape,
                    clip_denoised=args.clip_denoised,
                    model_kwargs={},
                    progress=True,
                    desc=(batch_desc_state, batch_desc_mask),
                    denoised_fn=denoised_fn
                )
            
            all_samples.append(samples)
            num_done = batch_end
            
        all_samples = th.cat(all_samples, dim=0).to(device)
        
        print("SMILES 解码中...")
        with th.no_grad():
            logits = model.get_logits(all_samples)
            # 限制预测概率的维度至有效词表大小（37），避免硬编码 312 导致解码出越界词
            logits = logits[..., :len(tokenizer)]
            cands = th.topk(logits, k=1, dim=-1)
            token_ids = cands.indices.squeeze(-1)
            
        generated_smiles = tokenizer.decode(token_ids)
        
        csv_path = os.path.join(args.output_dir, f"generated_{target}.csv")
        print(f"保存分子到: {csv_path}")
        
        with open(csv_path, mode='w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(['SMILES'])
            
            valid_count = 0
            for smi in generated_smiles:
                smi_clean = sanitize_smiles(smi)
                if not smi_clean or not is_valid_smiles(smi_clean):
                    smi_clean = "INVALID"
                else:
                    valid_count += 1
                writer.writerow([smi_clean])
                
        print(f"靶标 {target} 生成完毕！有效分子比例: {valid_count}/{args.num_samples} ({valid_count/args.num_samples*100:.2f}%)")

def create_argparser():
    defaults = dict(
        clip_denoised=False,
        num_samples=10,
        batch_size=2,
        use_ddim=False,
        timestep_spacing=10,
        model_path="../../checkpoints_protein_170_self_cond/PLAIN_ema_0.9999_200000.pt",  # 指向自条件化 checkpoint
        esm2_path="../../esm2_t30_150M_UR50D",
        fasta_dir="../../datasets/fasta",
        projection_weights_path="",
        target_protein="all",
        output_dir="../../generation_results",
        emb_scale_factor=1.0,
        clamp="clamp",
        clamp_thresh=350,
        clamp_top_k=5,
        clamp_temp=0.1,
        clamp_soft=True,
        self_cond=True  # 新增 self_cond 命令行参数，默认为 True
    )
    
    parser = argparse.ArgumentParser(description="Generate SMILES guided by 12 target protein fasta sequences using Soft-Clamping (170-length) with Self-Conditioning")
    add_dict_to_argparser(parser, defaults)
    return parser

def add_dict_to_argparser(parser, default_dict):
    for k, v in default_dict.items():
        v_type = type(v)
        if v is None:
            v_type = str
        elif isinstance(v, bool):
            v_type = str2bool
        parser.add_argument(f"--{k}", default=v, type=v_type)

def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ("yes", "true", "t", "y", "1"):
        return True
    elif v.lower() in ("no", "false", "f", "n", "0"):
        return False
    else:
        raise argparse.ArgumentTypeError(f"Boolean value expected, got {v}")

if __name__ == "__main__":
    main()
