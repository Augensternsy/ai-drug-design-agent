"""
Generate MODEL_MANIFEST.sha256 and BACKUP_MANIFEST.md for drug-design-agent.
"""
import hashlib
import os
from pathlib import Path

PROJECT_ROOT = Path("/mnt/harddisk/wsy/drug-design-agent")

KEY_FILES = [
    "models/e2po/direct_ki_e2po_15k.pt",
    "models/esm2/pytorch_model.bin",
    "models/tokenizer/vocab.json",
    "models/bert-base-uncased/config.json",
    "data/target_data_eval/ESR1.csv",
    "data/structures/2r6w/2r6w_protein_cleaned.pdbqt"
]

def sha256_file(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192 * 1024):
            h.update(chunk)
    return h.hexdigest()

def main():
    manifest_lines = []
    print("Calculating SHA256 for key model and structure files...")
    
    for rel_path in KEY_FILES:
        full_path = PROJECT_ROOT / rel_path
        if full_path.exists():
            digest = sha256_file(full_path)
            size_mb = full_path.stat().st_size / (1024 * 1024)
            manifest_lines.append(f"{digest}  {rel_path}")
            print(f"  {rel_path} ({size_mb:.2f} MB): {digest}")

    sha256_file_path = PROJECT_ROOT / "MODEL_MANIFEST.sha256"
    with open(sha256_file_path, "w") as f:
        f.write("\n".join(manifest_lines) + "\n")

    # Generate BACKUP_MANIFEST.md
    backup_manifest_content = f"""# BACKUP MANIFEST — AI Drug Design Agent v2

Generated on: 2026-09-08
Project: `/mnt/harddisk/wsy/drug-design-agent`

## Core Active Configuration
- **Model Checkpoint**: `models/e2po/direct_ki_e2po_15k.pt`
- **ESM-2 Encoder**: `models/esm2/`
- **Sampling Steps**: 200
- **Clamp Mode**: none

## Key File SHA256 Checksums

```text
""" + "\n".join(manifest_lines) + """
```

## Backup Inclusion Summary
- **Private Backup (`drug-design-agent-backup.tar.gz`)**: Includes full source code, API service, scripts, demo data, protein structures, tokenizer, bert-base config, ESM-2 weights, and direct_ki_e2po_15k.pt checkpoint.
- **GitHub Code Package (`drug-design-agent-github.tar.gz`)**: Includes source code, README, DEPLOYMENT.md, Dockerfile, requirements.txt, .env.example, API routes, and demo data. Excludes all `.pt`, `.bin`, `.safetensors`, `.env`, logs, and temporary outputs.
"""

    backup_manifest_path = PROJECT_ROOT / "BACKUP_MANIFEST.md"
    with open(backup_manifest_path, "w") as f:
        f.write(backup_manifest_content)

    print(f"Generated {sha256_file_path.name} and {backup_manifest_path.name} successfully.")

if __name__ == "__main__":
    main()
