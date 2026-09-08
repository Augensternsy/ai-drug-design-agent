import torch
import torch.nn as nn
import pandas as pd
import numpy as np
import json
import pickle
from transformers import AutoModel, AutoTokenizer
import argparse
import os
import sys
import time

class ESM2ProjectionLayer(nn.Module):
    """
    将 ESM-2 的输出映射到 TGM-DLM 需要的 1024 维
    """
    def __init__(self, input_dim=640, output_dim=1024):
        super().__init__()
        self.proj = nn.Sequential(
            nn.Linear(input_dim, output_dim),
            nn.GELU(),
            nn.Linear(output_dim, output_dim)
        )

    def forward(self, x):
        return self.proj(x)

def load_sequence_mapping(mapping_path):
    print(f"Loading sequence mapping from: {mapping_path}")
    with open(mapping_path, 'r') as f:
        mappings = json.load(f)
    if 'sequence' not in mappings:
        raise ValueError("mapping 文件中缺少 'sequence' 键")
    sequence_mapping = {v: k for k, v in mappings['sequence'].items()}
    print(f"Loaded {len(sequence_mapping)} unique sequences")
    return sequence_mapping


def load_sequence_and_smiles_mapping(mapping_path):
    """加载序列和SMILES的双向映射"""
    print(f"Loading sequence and smiles mapping from: {mapping_path}")
    with open(mapping_path, 'r') as f:
        mappings = json.load(f)

    if 'sequence' not in mappings:
        raise ValueError("mapping 文件中缺少 'sequence' 键")
    if 'smiles' not in mappings:
        raise ValueError("mapping 文件中缺少 'smiles' 键")

    # 创建索引到序列/字符串的反向映射
    sequence_mapping = {v: k for k, v in mappings['sequence'].items()}
    smiles_mapping = {v: k for k, v in mappings['smiles'].items()}

    print(f"Loaded {len(sequence_mapping)} unique sequences")
    print(f"Loaded {len(smiles_mapping)} unique smiles")
    return sequence_mapping, smiles_mapping

def generate_protein_embeddings_from_csv(csv_path, output_dir, model_name="../../esm2_t30_150M_UR50D",
                                         batch_size=16, target_dim=1024, max_length=256):
    """
    直接将每条处理好的数据保存为独立文件，彻底告别内存泄漏。
    """
    dataset_dir = os.path.dirname(csv_path)
    mapping_path = os.path.join(dataset_dir, 'categorical_mappings.json')
    sequence_mapping = load_sequence_mapping(mapping_path)

    df = pd.read_csv(csv_path)
    total_samples = len(df)
    print(f"Total samples: {total_samples}")

    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)
    model.eval()

    projection_layer = ESM2ProjectionLayer(input_dim=model.config.hidden_size, output_dim=target_dim)
    projection_layer.eval()

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model = model.to(device)
    projection_layer = projection_layer.to(device)

    os.makedirs(output_dir, exist_ok=True)

    # 筛选未处理的数据
    data_pairs = []
    processed_count = 0
    for idx, row in df.iterrows():
        seq_index = row['sequence']
        if seq_index in sequence_mapping:
            # 根据 idx 计算子文件夹，每 10000 个文件放在一个文件夹内，防止单文件夹文件过多系统卡顿
            folder_idx = idx // 10000
            file_path = os.path.join(output_dir, f"{folder_idx:04d}", f"{idx}.pt")

            if not os.path.exists(file_path):
                data_pairs.append((idx, sequence_mapping[seq_index], file_path))
            else:
                processed_count += 1

    total_to_process = len(data_pairs)
    print(f"Already processed: {processed_count}")
    print(f"Need to process: {total_to_process}")

    if total_to_process == 0:
        return

    start_time = time.time()
    for batch_idx in range(0, total_to_process, batch_size):
        batch_data = data_pairs[batch_idx:batch_idx + batch_size]
        batch_indices = [item[0] for item in batch_data]
        batch_sequences = [item[1] for item in batch_data]
        batch_paths = [item[2] for item in batch_data]

        try:
            inputs = tokenizer(
                batch_sequences,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=max_length
            ).to(device)

            with torch.no_grad():
                outputs = model(**inputs)
                token_embeddings = outputs.last_hidden_state
                token_embeddings = projection_layer(token_embeddings)

            attention_mask = inputs['attention_mask'].cpu()

            # 遍历 Batch 逐个保存
            for j, file_path in enumerate(batch_paths):
                # 只截取有效长度 (丢弃冗余的 Padding)，显著减小磁盘占用
                seq_len = int(attention_mask[j].sum().item())

                # 转换为半精度 float16，内存占用立刻减半
                states = token_embeddings[j, :seq_len, :].half().cpu()
                mask = attention_mask[j, :seq_len].cpu()

                # 确保子目录存在
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                torch.save({'states': states, 'mask': mask}, file_path)

            # 清理显存
            del inputs, outputs, token_embeddings, attention_mask
            if device.type == 'cuda':
                torch.cuda.empty_cache()

            current_total = batch_idx + len(batch_data)
            if current_total % 1000 == 0 or current_total >= total_to_process:
                elapsed = time.time() - start_time
                avg_time = elapsed / current_total
                remaining_time = avg_time * (total_to_process - current_total)
                print(f"[Processed {current_total}/{total_to_process}] | Elapsed: {elapsed:.1f}s | Remaining: {remaining_time:.1}s")

        except Exception as e:
            print(f"Error processing batch starting at index {batch_indices[0]}: {str(e)}")
            continue

    print("\nData generation fully complete!")

# ================= 修改后的 Dataset =================
class TrainCSVDataset:
    def __init__(self, dir, smi_tokenizer, csv_path, replace_desc=False, load_state=True,
                 corrupt_prob=0.4, mask_desc=False, max_desc_length=256):
        self.dir = dir
        self.smi_tokenizer = smi_tokenizer
        self.csv_path = csv_path
        self.corrupt_prob = corrupt_prob
        self.mask_desc = mask_desc
        self.max_desc_length = max_desc_length # 需要知道最大长度以便补全 padding

        self.mapping_path = os.path.join(dir, 'categorical_mappings.json')
        self.sequence_mapping, self.smiles_mapping = load_sequence_and_smiles_mapping(self.mapping_path)
        self.ori_data = self.get_ori_data()
        self.load_state = load_state
        self.states_dir = os.path.join(self.dir, 'output', 'train_desc_states') # 新的特征存放根目录

    def get_ori_data(self):
        res = []
        df = pd.read_csv(self.csv_path)
        for idx, row in df.iterrows():
            smiles_index = row['smiles']
            smiles = self.smiles_mapping.get(smiles_index, "")
            seq_index = row['sequence']
            sequence = self.sequence_mapping.get(seq_index, "")
            label = row['label'] if 'label' in row else 1
            res.append((idx, smiles, sequence, label))
        return res

    def __getitem__(self, idx):
        data = self.ori_data[idx]
        dic = {
            'cid': data[0],
            'smiles': data[1],
            'desc': data[2],
            'label': data[3]
        }
        dic['tok_smiles'] = self.smi_tokenizer(dic['smiles'])
        dic['corrupted_toked_smis'] = self.smi_tokenizer.corrupt(dic['smiles']) if torch.rand(1).item() < self.corrupt_prob else dic['tok_smiles']

        # 初始化默认的零张量（确保不会返回 None）
        # 3D张量 [1, max_desc_length, 1024]
        dic['desc_state'] = torch.zeros(1, self.max_desc_length, 1024)
        dic['desc_mask'] = torch.zeros(1, self.max_desc_length)

        # 动态读取并恢复 Padding
        if self.load_state:
            folder_idx = data[0] // 10000
            file_path = os.path.join(self.states_dir, f"{folder_idx:04d}", f"{data[0]}.pt")

            if os.path.exists(file_path):
                try:
                    # 检查文件是否为空
                    if os.path.getsize(file_path) == 0:
                        print(f"Warning: Empty file {file_path}, using default desc_state")
                    else:
                        # 读取时会是 fp16，恢复回模型期望的 fp32
                        state_data = torch.load(file_path, weights_only=False)
                        states = state_data['states'].float() # [seq_len, 1024]
                        mask = state_data['mask']             # [seq_len]

                        # 动态补齐 Padding 使得 Dataloader 可以顺利拼接 Batch
                        pad_len = self.max_desc_length - states.shape[0]
                        if pad_len > 0:
                            states = torch.nn.functional.pad(states, (0, 0, 0, pad_len))
                            mask = torch.nn.functional.pad(mask, (0, pad_len))

                        # 变成三维张量 [1, seq_len, dim] 和二维张量 [1, seq_len]
                        dic['desc_state'] = states.unsqueeze(0)
                        dic['desc_mask'] = mask.unsqueeze(0)
                except (EOFError, RuntimeError, pickle.UnpicklingError, KeyError) as e:
                    # 【核心修复】：如果遇到损坏的 .pt 文件，打印警告并返回全0张量，绝不崩溃
                    print(f"\n[Warning] 发现损坏的特征文件，已自动跳过: {file_path}")
                    states = torch.zeros((self.max_desc_length, 1024), dtype=torch.float32)
                    mask = torch.zeros((self.max_desc_length,), dtype=torch.long)
                    dic['desc_state'] = states.unsqueeze(0)
                    dic['desc_mask'] = mask.unsqueeze(0)

            if self.mask_desc:
                dic['desc_state'] = torch.zeros_like(dic['desc_state'])
                dic['desc_mask'] = torch.ones_like(dic['desc_mask'])

        return dic

    def __len__(self):
        return len(self.ori_data)

def main():
    parser = argparse.ArgumentParser(description='Process train.csv for 2D protein embedding generation')
    parser.add_argument('--csv_path', type=str, default='../../datasets/train.csv')
    parser.add_argument('--output_dir', type=str, default='../../datasets/output/train_desc_states',
                        help='Directory to save sharded .pt files')
    parser.add_argument('--esm2_path', type=str, default='../../esm2_t30_150M_UR50D')
    parser.add_argument('--batch_size', type=int, default=16)
    parser.add_argument('--target_dim', type=int, default=1024)
    parser.add_argument('--max_length', type=int, default=256)
    args = parser.parse_args()

    generate_protein_embeddings_from_csv(
        csv_path=args.csv_path,
        output_dir=args.output_dir,
        model_name=args.esm2_path,
        batch_size=args.batch_size,
        target_dim=args.target_dim,
        max_length=args.max_length
    )

if __name__ == '__main__':
    main()