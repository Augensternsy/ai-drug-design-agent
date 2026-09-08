# RunPod Private Asset Manifest

This manifest defines the private runtime assets that must be uploaded to the RunPod Network Volume. The assets are deliberately excluded from GitHub.

## Curated archive

```text
Filename: runpod-assets.tar.gz
Compressed size: 1,028,874,701 bytes (0.958 GiB)
Archive entries: 46
SHA-256: 31c926aa70e03dfac4939ba1e349f14fa6cabea8ee553c00577b775f2b83d199
Extract to: /workspace
```

The selected files total 1,330,596,281 bytes before gzip compression.

## Required model assets

| Runtime component | Archive path | Files | Bytes | Requirement |
|---|---|---:|---:|---|
| DLPS-E2PO checkpoint | `models/e2po/direct_ki_e2po_15k.pt` | 1 | 731,576,807 | Required |
| ESM-2 model + tokenizer metadata | `models/esm2/` | 5 | 595,365,169 | Required |
| Chemformer tokenizer helper | `models/tokenizer/mytokenizers.py` | 1 | 16,484 | Included for asset completeness; runtime implementation is also in public source |
| BERT architecture config | `models/bert-base-uncased/config.json` | 1 | 570 | Required by `AutoConfig`; BERT weights are not required |

Critical hashes:

| Path | SHA-256 |
|---|---|
| `models/e2po/direct_ki_e2po_15k.pt` | `2bd5e18825308b15a5f07ba31d3ead3ca3f7351e1984f9c6f5e9f2a6476582e8` |
| `models/esm2/pytorch_model.bin` | `a88feb574b9f4e31c45762961d1b2ddba95796db86fb480d207b4d15e6ec8aab` |
| `models/bert-base-uncased/config.json` | `7160e1553ad2ca51d8c1cb066be533db31826e12d173824c1bb0cb1a4f187d20` |
| `models/tokenizer/mytokenizers.py` | `0922e4c44917290d7ee0d432ca211c395e23be3729b9391635eefcae7c210121` |

The ESM-2 directory contains:

```text
models/esm2/
├── config.json
├── pytorch_model.bin
├── special_tokens_map.json
├── tokenizer_config.json
└── vocab.txt
```

## Required target and docking data

| Runtime component | Archive path | Files | Bytes |
|---|---|---:|---:|
| 12 target metadata and FASTA sequences | `data/targets/` | 14 | 17,064 |
| AutoDock Vina receptors and reference ligands | `data/structures/` | 24 | 3,620,187 |

The 12 target/PDB pairs are:

| Target | PDB ID | Required structure files |
|---|---|---|
| ESR1 | 2r6w | `2r6w_protein_cleaned.pdbqt`, `2r6w_ligand.sdf` |
| HCRTR1 | 4zjc | `4zjc_protein_cleaned.pdbqt`, `4zjc_ligand.sdf` |
| JAK1 | 3eyg | `3eyg_protein_cleaned.pdbqt`, `3eyg_ligand.sdf` |
| P2RX3 | 5svl | `5svl_protein_cleaned.pdbqt`, `5svl_ligand.sdf` |
| KDM1A | 5lhg | `5lhg_protein_cleaned.pdbqt`, `5lhg_ligand.sdf` |
| IDH1 | 4umx | `4umx_protein_cleaned.pdbqt`, `4umx_ligand.sdf` |
| RIOK1 | 4otp | `4otp_protein_cleaned.pdbqt`, `4otp_ligand.sdf` |
| NR4A1 | 3v3q | `3v3q_protein_cleaned.pdbqt`, `3v3q_ligand.sdf` |
| GRIK1 | 3fv1 | `3fv1_protein_cleaned.pdbqt`, `3fv1_ligand.sdf` |
| CCR9 | 5lwe | `5lwe_protein_cleaned.pdbqt`, `5lwe_ligand.sdf` |
| FTO | 4zs3 | `4zs3_protein_cleaned.pdbqt`, `4zs3_ligand.sdf` |
| SPIN1 | 5jsj | `5jsj_protein_cleaned.pdbqt`, `5jsj_ligand.sdf` |

The PDBQT receptor and SDF reference ligand are the two files used by the current Python Vina workflow for each target.

## Deliberately excluded from the archive

- Base/SFT checkpoint `models/base/PLAIN_ema_0.9999_050000.pt`.
- All BERT weights and exports (`.bin`, `.safetensors`, `.onnx`, `.h5`, `.ot`, `.msgpack`, Core ML).
- `data/precomputed/` experiment and fallback results.
- Cleaned receptor `.pdb` files; the runtime uses `.pdbqt` receptors.
- Outputs, logs, caches, temporary docking files, bytecode and environment secrets.

## Required RunPod layout after extraction

```text
/workspace/models/e2po/direct_ki_e2po_15k.pt
/workspace/models/esm2/pytorch_model.bin
/workspace/models/bert-base-uncased/config.json
/workspace/models/tokenizer/mytokenizers.py
/workspace/data/targets/targets.json
/workspace/data/targets/fasta/<TARGET>.fasta
/workspace/data/structures/<PDB_ID>/<PDB_ID>_protein_cleaned.pdbqt
/workspace/data/structures/<PDB_ID>/<PDB_ID>_ligand.sdf
```
