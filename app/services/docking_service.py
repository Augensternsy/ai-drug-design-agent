"""
Docking Service — AutoDock Vina 对接封装

Pipeline:
  SMILES list + target
    → 3D conformer (RDKit)
    → PDBQT (Meeko)
    → AutoDock Vina (python-vina)
    → score extraction
    → return [{"smiles": ..., "vina_score": ..., "success": ...}]

依赖：
  - python-vina (pip install vina)
  - meeko (pip install meeko)
  - 预处理好的 receptor .pdbqt 文件（data/structures/{pdb_id}/{pdb_id}_protein_cleaned.pdbqt）
  - 配体参考文件用于计算对接盒子（data/structures/{pdb_id}/{pdb_id}_ligand.sdf）
"""

import os
import logging
import numpy as np
from typing import Optional

from app.config import (
    STRUCTURES_DIR, DEVICE,
    VINA_EXHAUSTIVENESS, VINA_N_POSES, VINA_BOX_PADDING,
)
from app.services.target_service import TargetRegistry

logger = logging.getLogger(__name__)

# Optional imports — graceful degradation
try:
    from vina import Vina
    VINA_AVAILABLE = True
except ImportError:
    Vina = None
    VINA_AVAILABLE = False

try:
    from meeko import MoleculePreparation, PDBQTWriterLegacy
    MEEKO_AVAILABLE = True
    MEEKO_IMPORT_ERROR = None
except ImportError as exc:
    MoleculePreparation = None
    PDBQTWriterLegacy = None
    MEEKO_AVAILABLE = False
    MEEKO_IMPORT_ERROR = exc


def is_docking_available() -> bool:
    return VINA_AVAILABLE and MEEKO_AVAILABLE


def get_receptor_path(target: str) -> Optional[str]:
    """Return path to receptor PDBQT for a target."""
    rec = TargetRegistry.get_receptor_path(target)
    return str(rec) if rec and rec.exists() else None


def get_ligand_ref_path(target: str) -> Optional[str]:
    """Return path to reference ligand SDF for box calculation."""
    lig = TargetRegistry.get_reference_ligand_path(target)
    return str(lig) if lig and lig.exists() else None


def compute_docking_box(ref_ligand_path: str) -> tuple[np.ndarray, np.ndarray]:
    """
    从参考配体 SDF 计算对接盒子中心和大小。
    与论文实验一致：BOX_PADDING = 10.0 Å
    """
    from rdkit import Chem
    mol = Chem.MolFromMolFile(ref_ligand_path)
    if not mol:
        raise ValueError(f"Cannot read ligand: {ref_ligand_path}")
    conf = mol.GetConformer()
    coords = conf.GetPositions()
    center = np.mean(coords, axis=0)
    size = (np.max(coords, axis=0) - np.min(coords, axis=0)) + VINA_BOX_PADDING
    return center, size


def prepare_ligand_pdbqt(smiles: str) -> Optional[str]:
    """
    SMILES → 3D conformer → PDBQT string via Meeko。
    """
    if not MEEKO_AVAILABLE:
        raise ImportError(f"meeko is required: {MEEKO_IMPORT_ERROR}")

    from rdkit import Chem
    from rdkit.Chem import AllChem

    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        return None

    mol = Chem.AddHs(mol)
    if AllChem.EmbedMolecule(mol, randomSeed=42) != 0:
        if AllChem.EmbedMolecule(mol, useRandomCoords=True) != 0:
            return None
    try:
        AllChem.UFFOptimizeMolecule(mol)
    except Exception:
        pass

    try:
        preparator = MoleculePreparation()
        mol_setups = preparator.prepare(mol)
        if not mol_setups:
            raise RuntimeError("Meeko returned no molecule setup")

        pdbqt_string, success, error_msg = PDBQTWriterLegacy.write_string(mol_setups[0])
        if not success:
            raise RuntimeError(f"Meeko PDBQT writer failed: {error_msg.strip()}")
        if not pdbqt_string.strip():
            raise RuntimeError("Meeko returned an empty PDBQT string")
        return pdbqt_string
    except Exception as exc:
        logger.exception(
            "Ligand PDBQT preparation failed for SMILES %s: %s",
            smiles,
            exc,
        )
        return None


def dock_single(
    smiles: str,
    receptor_path: str,
    center: np.ndarray,
    box_size: np.ndarray,
    exhaustiveness: int = VINA_EXHAUSTIVENESS,
    n_poses: int = VINA_N_POSES,
) -> dict:
    """
    对单个分子执行 Vina 对接。

    Returns:
        {"smiles": ..., "vina_score": float|None, "success": bool}
    """
    if not VINA_AVAILABLE:
        raise ImportError("python-vina is required: pip install vina")

    result = {"smiles": smiles, "vina_score": None, "success": False}

    from rdkit import Chem
    from rdkit.Chem import Descriptors, Lipinski

    mol = Chem.MolFromSmiles(smiles)
    if not mol:
        return result

    # 过滤过于复杂的分子（与论文一致）
    n_rot = Lipinski.NumRotatableBonds(mol)
    mw = Descriptors.MolWt(mol)
    if n_rot > 15 or mw > 750:
        return result

    pdbqt_str = prepare_ligand_pdbqt(smiles)
    if not pdbqt_str:
        result["error"] = "Ligand PDBQT preparation failed; see task logs"
        logger.error(
            "Vina docking skipped because ligand PDBQT preparation failed: %s",
            smiles,
        )
        return result

    try:
        v = Vina(sf_name="vina", cpu=1, verbosity=0)
        v.set_receptor(receptor_path)
        v.compute_vina_maps(center=center.tolist(), box_size=box_size.tolist())
        v.set_ligand_from_string(pdbqt_str)
        v.dock(exhaustiveness=exhaustiveness, n_poses=n_poses)
        score = v.score()[0]
        result["vina_score"] = float(score)
        result["success"] = True
    except Exception as e:
        result["error"] = f"{type(e).__name__}: {e}"
        logger.exception("Vina docking failed for SMILES %s: %s", smiles, e)

    return result


def dock_molecules(
    target_or_smiles: list[str] | str,
    smiles_or_receptor: list[str] | str,
    center: Optional[np.ndarray] = None,
    box_size: Optional[np.ndarray] = None,
    exhaustiveness: int = VINA_EXHAUSTIVENESS,
) -> list[dict]:
    """
    对一组分子执行 Vina 对接。
    支持两种调用方式：
    1. dock_molecules("ESR1", smiles_list)
    2. dock_molecules(smiles_list, receptor_path, center, box_size)
    """
    if not is_docking_available():
        raise ImportError("Docking requires: pip install vina meeko")

    if isinstance(target_or_smiles, str):
        target = target_or_smiles
        smiles_list = smiles_or_receptor
        receptor_path = get_receptor_path(target)
        if not receptor_path:
            raise FileNotFoundError(f"Receptor PDBQT not found for target: {target}")
        ref_lig_path = get_ligand_ref_path(target)
        if not ref_lig_path:
            raise FileNotFoundError(f"Reference ligand SDF not found for target: {target}")
        center, box_size = compute_docking_box(ref_lig_path)
    else:
        smiles_list = target_or_smiles
        receptor_path = smiles_or_receptor
        if center is None or box_size is None:
            raise ValueError("center and box_size must be specified if receptor_path is provided directly")

    results = []
    for smi in smiles_list:
        res = dock_single(smi, receptor_path, center, box_size, exhaustiveness)
        results.append(res)

    return results
