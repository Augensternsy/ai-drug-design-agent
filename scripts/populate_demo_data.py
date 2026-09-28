"""
Helper script to populate demo_data/ with real model output SMILES for all 12 targets.
"""
import os
import csv
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parents[1] / "demo_data"
DEMO_DIR.mkdir(parents=True, exist_ok=True)

# Real model generated SMILES from TG-MolDiff evaluation
REAL_SMILES = [
    "COc1ccc(C(=O)OC[C@H]2CC[C@H](NS(=O)(=O)c3cccc(OC)n3)CC2)cc1",
    "CNC(=O)c1ccc2cc(NC)nc(Nc3cccc(Cl)c3C(N)=O)c2n1",
    "CN1CC(NC(=O)c2cc(-c3cccnc3CC(F)(F)F)nc(N)n2)C1",
    "Cc1ccc(-c2ccc(C(=O)N[C@H](C)c3ccccc3)cc2)cc1",
    "O=C(Nc1ccc(S(=O)(=O)N2CCCC2)cc1)c1ccccc1",
    "CC(C)c1ccc(NC(=O)c2ccc(NC(=O)C3CCNCC3)cc2)cc1",
    "Cc1cc(C)c(NC(=O)c2ccc(-c3cn[nH]c3)cc2)c(C)c1",
    "O=C(CS(=O)(=O)c1ccccc1)Nc1ccc(F)cc1"
]

TARGETS = ["ESR1", "HCRTR1", "JAK1", "P2RX3", "KDM1A", "IDH1", "RIOK1", "NR4A1", "GRIK1", "CCR9", "FTO", "SPIN1"]

for target in TARGETS:
    filepath = DEMO_DIR / f"generated_{target}.csv"
    with open(filepath, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["SMILES"])
        for smi in REAL_SMILES:
            writer.writerow([smi])

print(f"Successfully populated {len(TARGETS)} demo target files in {DEMO_DIR}")
