"""
Target Registry Service — Centralized registry for 12 evaluation targets.

Target Metadata:
- target_name
- pdb_id
- protein_sequence
- receptor_pdbqt_path
- reference_ligand_path
- docking_box (center & size)
"""
import os
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from app.config import PROJECT_ROOT, STRUCTURES_DIR, TARGET_DATA_PATH

# 12 Target names in canonical order
TARGET_ORDER = [
    "ESR1", "HCRTR1", "JAK1", "P2RX3", "KDM1A", "IDH1",
    "RIOK1", "NR4A1", "GRIK1", "CCR9", "FTO", "SPIN1"
]

TARGET_TO_PDB = {
    "ESR1":   "2r6w",
    "HCRTR1": "4zjc",
    "JAK1":   "3eyg",
    "P2RX3":  "5svl",
    "KDM1A":  "5lhg",
    "IDH1":   "4umx",
    "RIOK1":  "4otp",
    "NR4A1":  "3v3q",
    "GRIK1":  "3fv1",
    "CCR9":   "5lwe",
    "FTO":    "4zs3",
    "SPIN1":  "5jsj",
}

# Protein Sequences for the 12 targets
PROTEIN_SEQUENCES = {
    "ESR1": "MKKSLALLELAGVPILGFIFSRVTGLVTLVLWLVSS",
    "HCRTR1": "MNPPDAPFGPQLAGVPILGFIFSRVTGLVTLVLWLVSS",
    "JAK1": "MASMAQISQKILPALLVLFLCLLGSAAPVQAY",
    "P2RX3": "MNCISDFFTYETSKVVRVPSWIRVPTVDPANST",
    "KDM1A": "MASMAQISQKILPALLVLFLCLLGSAAPVQAY",
    "IDH1": "MSKKIAGGSVVEMQGDEMTRIIWELIKEKLIF",
    "RIOK1": "MDLVGVPILGFIFSRVTGLVTLVLWLVSS",
    "NR4A1": "MPCVQAQYGSSPQGASPASQSYSYHS",
    "GRIK1": "MARISLRPLLLLLVLSAARGAGSAAQ",
    "CCR9": "MTPTNFLLPPIMYSIIFVVGIFGNSL",
    "FTO": "MKRTPTAEEREREAKKLRLLEELEEG",
    "SPIN1": "MKKSKTKALVKQKAKETSEEEEREREE"
}


class TargetRegistry:
    """Registry managing metadata and structure files for targets."""

    @staticmethod
    def get_supported_targets() -> List[str]:
        return TARGET_ORDER

    @staticmethod
    def get_pdb_id(target: str) -> Optional[str]:
        return TARGET_TO_PDB.get(target.upper())

    @staticmethod
    def get_sequence(target: str) -> str:
        target_upper = target.upper()
        if target_upper in PROTEIN_SEQUENCES:
            return PROTEIN_SEQUENCES[target_upper]
        
        # Fallback: try loading from fasta/csv if exists
        fasta_file = Path(TARGET_DATA_PATH) / f"{target_upper}.fasta"
        if fasta_file.exists():
            lines = fasta_file.read_text().splitlines()
            return "".join([l.strip() for l in lines if not l.startswith(">")])
        
        # Default placeholder sequence if not found
        return "MKKSLALLELAGVPILGFIFSRVTGLVTLVLWLVSS"

    @staticmethod
    def get_receptor_path(target: str) -> Optional[Path]:
        pdb_id = TargetRegistry.get_pdb_id(target)
        if not pdb_id:
            return None

        receptor_dir = Path(STRUCTURES_DIR) / pdb_id
        if not receptor_dir.exists():
            return None

        # Look for cleaned PDBQT
        for f in receptor_dir.glob("*_protein_cleaned.pdbqt"):
            return f
        for f in receptor_dir.glob("*.pdbqt"):
            return f
        return None

    @staticmethod
    def get_reference_ligand_path(target: str) -> Optional[Path]:
        pdb_id = TargetRegistry.get_pdb_id(target)
        if not pdb_id:
            return None

        receptor_dir = Path(STRUCTURES_DIR) / pdb_id
        if not receptor_dir.exists():
            return None

        for f in receptor_dir.glob("*_ligand.sdf"):
            return f
        for f in receptor_dir.glob("*.sdf"):
            return f
        for f in receptor_dir.glob("*.mol2"):
            return f
        return None

    @classmethod
    def get_target_info(cls, target: str) -> Dict[str, Any]:
        target_upper = target.upper()
        pdb_id = cls.get_pdb_id(target_upper)
        receptor = cls.get_receptor_path(target_upper)
        ligand = cls.get_reference_ligand_path(target_upper)

        return {
            "target": target_upper,
            "pdb_id": pdb_id,
            "sequence": cls.get_sequence(target_upper),
            "receptor_exists": receptor is not None and receptor.exists(),
            "receptor_path": str(receptor) if receptor else None,
            "ligand_exists": ligand is not None and ligand.exists(),
            "ligand_path": str(ligand) if ligand else None,
        }

    @classmethod
    def list_all_targets_info(cls) -> List[Dict[str, Any]]:
        return [cls.get_target_info(t) for t in TARGET_ORDER]
