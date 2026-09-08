"""
Extract raw ESM-2 protein sequence embeddings using standard transformers.
"""
import argparse
import os
import torch as th
from transformers import AutoModel, AutoTokenizer

def parse_fasta(fpath):
    with open(fpath, 'r') as f:
        lines = f.readlines()
    seq = ''.join([line.strip() for line in lines if not line.startswith('>')])
    return seq

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fasta_dir", type=str, default="../../datasets/fasta")
    parser.add_argument("--esm2_path", type=str, default="../../esm2_t30_150M_UR50D")
    parser.add_argument("--output_file", type=str, default="../../generation_results/esm_raw_embeddings.pt")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output_file), exist_ok=True)

    device = th.device("cuda:0" if th.cuda.is_available() else "cpu")
    print(f"[ESM Subprocess] Loading ESM-2 model from: {args.esm2_path} on {device}")
    tokenizer = AutoTokenizer.from_pretrained(args.esm2_path)
    model = AutoModel.from_pretrained(args.esm2_path).to(device)
    model.eval()

    name_order = ['ESR1', 'HCRTR1', 'JAK1', 'P2RX3', 'KDM1A', 'IDH1', 'RIOK1', 'NR4A1', 'GRIK1', 'CCR9', 'FTO', 'SPIN1']
    raw_embeddings = {}

    for target in name_order:
        fasta_path = os.path.join(args.fasta_dir, f"{target}.fasta")
        if not os.path.exists(fasta_path):
            print(f"[ESM Subprocess] Fasta file not found for {target}: {fasta_path}")
            continue

        seq = parse_fasta(fasta_path)
        print(f"[ESM Subprocess] Encoding sequence for {target} (length: {len(seq)})...")

        inputs = tokenizer(
            [seq],
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=512
        ).to(device)

        with th.no_grad():
            outputs = model(**inputs)
            token_embeddings = outputs.last_hidden_state
            attention_mask = inputs['attention_mask'].cpu()
            
            seq_len = int(attention_mask[0].sum().item())
            states = token_embeddings[0, :seq_len, :].float().cpu()
            mask = attention_mask[0, :seq_len].cpu()
            
            raw_embeddings[target] = {
                'states': states,
                'mask': mask
            }

    print(f"[ESM Subprocess] Saving raw embeddings to: {args.output_file}")
    th.save(raw_embeddings, args.output_file)
    print("[ESM Subprocess] Done!")

if __name__ == "__main__":
    main()
