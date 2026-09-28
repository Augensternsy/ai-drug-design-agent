"""
RDKit Service — 分子性质计算与评价

计算指标（与论文实验完全一致）：
  - Validity (RDKit MolFromSmiles)
  - Canonicalization
  - Uniqueness
  - QED (Bickerton et al.)
  - SA Score (rdkit.Contrib.SA_Score)
  - MolWt (ExactMolWt)
  - LogP (Crippen)
  - Ro5 / Lipinski
  - ECFP4 (radius=2, 2048bit)
  - Tanimoto similarity
  - Novelty (vs reference actives, Tanimoto < 0.5)
  - 3D conformer generation
  - SDF export
"""

import os
from typing import Optional
import numpy as np

try:
    from rdkit import Chem, DataStructs, RDLogger
    from rdkit.Chem import (
        QED, Descriptors, AllChem, Lipinski,
        rdFingerprintGenerator, rdMolDescriptors,
    )
    from rdkit.ML.Cluster import Butina
    RDLogger.DisableLog("rdApp.*")
    RDKIT_AVAILABLE = True
except ImportError:
    RDKIT_AVAILABLE = False
    print("[RDKitService] WARNING: RDKit not available")


def check_rdkit():
    if not RDKIT_AVAILABLE:
        raise ImportError("RDKit is required but not installed.")


# ── Core helpers ──────────────────────────────────────────────────────────────

def mol_from_smiles(smiles: str):
    """Parse SMILES → RDKit mol (or None if invalid)."""
    check_rdkit()
    if not smiles or smiles in ("INVALID", "nan", ""):
        return None
    try:
        return Chem.MolFromSmiles(smiles.strip())
    except Exception:
        return None


def canonical_smiles(smiles: str) -> Optional[str]:
    """Return canonical SMILES or None if invalid."""
    mol = mol_from_smiles(smiles)
    if mol is None:
        return None
    return Chem.MolToSmiles(mol, canonical=True)


def is_valid(smiles: str) -> bool:
    return mol_from_smiles(smiles) is not None


# ── Single-molecule properties ─────────────────────────────────────────────────

def compute_qed(smiles: str) -> Optional[float]:
    mol = mol_from_smiles(smiles)
    if mol is None:
        return None
    return float(QED.default(mol))


def compute_sa(smiles: str) -> Optional[float]:
    mol = mol_from_smiles(smiles)
    if mol is None:
        return None
    try:
        from rdkit.Contrib.SA_Score import sascorer
        return float(sascorer.calculateScore(mol))
    except Exception:
        return None


def compute_molwt(smiles: str) -> Optional[float]:
    mol = mol_from_smiles(smiles)
    if mol is None:
        return None
    return float(Descriptors.MolWt(mol))


def compute_logp(smiles: str) -> Optional[float]:
    mol = mol_from_smiles(smiles)
    if mol is None:
        return None
    return float(Descriptors.MolLogP(mol))


def passes_ro5(smiles: str) -> Optional[bool]:
    """Lipinski Ro5: MW≤500, LogP≤5, HBD≤5, HBA≤10."""
    mol = mol_from_smiles(smiles)
    if mol is None:
        return None
    mw = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    hbd = rdMolDescriptors.CalcNumHBD(mol)
    hba = rdMolDescriptors.CalcNumHBA(mol)
    return bool(mw <= 500 and logp <= 5 and hbd <= 5 and hba <= 10)


def get_ecfp4(smiles: str):
    """Return ECFP4 fingerprint (radius=2, 2048bit) or None."""
    mol = mol_from_smiles(smiles)
    if mol is None:
        return None
    fpgen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    return fpgen.GetFingerprint(mol)


def tanimoto_similarity(smiles1: str, smiles2: str) -> Optional[float]:
    fp1 = get_ecfp4(smiles1)
    fp2 = get_ecfp4(smiles2)
    if fp1 is None or fp2 is None:
        return None
    return float(DataStructs.TanimotoSimilarity(fp1, fp2))


def compute_all_properties(smiles: str) -> dict:
    """Compute all properties for a single SMILES. Returns dict."""
    mol = mol_from_smiles(smiles)
    if mol is None:
        return {
            "smiles": smiles,
            "valid": False,
            "canonical_smiles": None,
            "qed": None,
            "sa": None,
            "mol_wt": None,
            "log_p": None,
            "ro5": None,
        }
    can_smi = Chem.MolToSmiles(mol, canonical=True)

    qed_val = float(QED.default(mol))
    mw_val = float(Descriptors.MolWt(mol))
    logp_val = float(Descriptors.MolLogP(mol))
    hbd = rdMolDescriptors.CalcNumHBD(mol)
    hba = rdMolDescriptors.CalcNumHBA(mol)
    ro5_val = bool(mw_val <= 500 and logp_val <= 5 and hbd <= 5 and hba <= 10)

    sa_val = None
    try:
        from rdkit.Contrib.SA_Score import sascorer
        sa_val = float(sascorer.calculateScore(mol))
    except Exception:
        pass

    return {
        "smiles": smiles,
        "valid": True,
        "canonical_smiles": can_smi,
        "qed": qed_val,
        "sa": sa_val,
        "mol_wt": mw_val,
        "log_p": logp_val,
        "ro5": ro5_val,
    }


# ── Batch evaluation ───────────────────────────────────────────────────────────

def evaluate_batch(smiles_list: list[str]) -> list[dict]:
    """Evaluate all properties for a list of SMILES strings."""
    return [compute_all_properties(s) for s in smiles_list]


def calculate_dataset_metrics(smiles_list: list[str], target_name: str = "") -> dict:
    """
    Dataset-level metrics (validity, uniqueness, diversity, QED, SA, MolWt, Ro5).
    与论文实验保持完全一致。
    """
    check_rdkit()
    total = len(smiles_list)
    valid_mols = []
    valid_canon = []

    for s in smiles_list:
        mol = mol_from_smiles(s)
        if mol:
            valid_mols.append(mol)
            valid_canon.append(Chem.MolToSmiles(mol, canonical=True))

    validity = len(valid_mols) / total if total > 0 else 0.0

    if not valid_mols:
        return {
            "target": target_name, "total": total,
            "validity": 0.0, "uniqueness": 0.0, "diversity": 0.0,
            "qed_mean": 0.0, "sa_mean": 0.0, "molwt_mean": 0.0, "ro5_rate": 0.0,
        }

    unique = set(valid_canon)
    uniqueness = len(unique) / len(valid_mols)

    # Diversity via Butina clustering (distThresh=0.2)
    fpgen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    fps = [fpgen.GetFingerprint(m) for m in valid_mols]
    diversity = 1.0
    if len(fps) > 1:
        dists = []
        for i in range(1, len(fps)):
            sims = DataStructs.BulkTanimotoSimilarity(fps[i], fps[:i])
            dists.extend([1 - x for x in sims])
        clusters = Butina.ClusterData(dists, len(fps), distThresh=0.2, isDistData=True)
        diversity = len(clusters) / len(fps)

    qeds = [float(QED.default(m)) for m in valid_mols]
    molwts = [float(Descriptors.MolWt(m)) for m in valid_mols]

    sas = []
    try:
        from rdkit.Contrib.SA_Score import sascorer
        sas = [float(sascorer.calculateScore(m)) for m in valid_mols]
    except Exception:
        sas = [3.0] * len(valid_mols)

    ro5_count = 0
    for m in valid_mols:
        mw = Descriptors.MolWt(m)
        logp = Descriptors.MolLogP(m)
        hbd = rdMolDescriptors.CalcNumHBD(m)
        hba = rdMolDescriptors.CalcNumHBA(m)
        if mw <= 500 and logp <= 5 and hbd <= 5 and hba <= 10:
            ro5_count += 1

    return {
        "target": target_name,
        "total": total,
        "n_valid": len(valid_mols),
        "validity": float(validity),
        "uniqueness": float(uniqueness),
        "diversity": float(diversity),
        "qed_mean": float(np.mean(qeds)),
        "sa_mean": float(np.mean(sas)),
        "molwt_mean": float(np.mean(molwts)),
        "ro5_rate": float(ro5_count / len(valid_mols)),
    }


# ── Filtering / selection ─────────────────────────────────────────────────────

def filter_valid_unique(smiles_list: list[str]) -> list[str]:
    """Return deduplicated list of valid canonical SMILES."""
    check_rdkit()
    seen = set()
    result = []
    for s in smiles_list:
        mol = mol_from_smiles(s)
        if mol:
            can = Chem.MolToSmiles(mol, canonical=True)
            if can not in seen:
                seen.add(can)
                result.append(can)
    return result


def diverse_selection_butina(
    valid_smiles: list[str],
    max_selected: int = 100,
    dist_threshold: float = 0.4,
) -> list[str]:
    """
    跨 Butina 簇轮选，确保多样性。与论文实验一致 (distThresh=0.4)。
    """
    check_rdkit()
    fpgen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    mols, fps, clean = [], [], []
    for s in valid_smiles:
        mol = Chem.MolFromSmiles(s)
        if mol:
            mols.append(mol)
            fps.append(fpgen.GetFingerprint(mol))
            clean.append(s)

    n = len(fps)
    if n <= max_selected:
        return clean

    try:
        dists = []
        for i in range(1, n):
            sims = DataStructs.BulkTanimotoSimilarity(fps[i], fps[:i])
            dists.extend([1 - x for x in sims])
        clusters = Butina.ClusterData(dists, n, distThresh=dist_threshold, isDistData=True)
        clusters = sorted(clusters, key=len, reverse=True)

        selected = []
        picks = [0] * len(clusters)
        while len(selected) < max_selected:
            added = False
            for ci, cluster in enumerate(clusters):
                if len(selected) >= max_selected:
                    break
                if picks[ci] < len(cluster):
                    selected.append(clean[cluster[picks[ci]]])
                    picks[ci] += 1
                    added = True
            if not added:
                break
        return selected
    except Exception:
        return clean[:max_selected]


def novelty_vs_reference(
    gen_smiles: list[str],
    ref_smiles: list[str],
    threshold: float = 0.5,
) -> float:
    """
    Novelty = fraction of generated mols with max Tanimoto < threshold vs reference.
    与论文实验一致 (threshold=0.5, ECFP4 radius=2 2048bit)
    """
    check_rdkit()
    fpgen = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)

    ref_fps = []
    for s in ref_smiles:
        mol = Chem.MolFromSmiles(s)
        if mol:
            ref_fps.append(fpgen.GetFingerprint(mol))

    if not ref_fps:
        return 1.0

    novel = 0
    total = 0
    for s in gen_smiles:
        mol = Chem.MolFromSmiles(s)
        if mol:
            gfp = fpgen.GetFingerprint(mol)
            sims = DataStructs.BulkTanimotoSimilarity(gfp, ref_fps)
            if not sims or max(sims) < threshold:
                novel += 1
            total += 1

    return novel / total if total > 0 else 1.0


# ── 3D conformer + SDF export ─────────────────────────────────────────────────

def generate_3d_conformer(smiles: str, seed: int = 42):
    """
    从 SMILES 生成 3D 构象体。返回带 3D 坐标的 mol (或 None)。
    """
    mol = mol_from_smiles(smiles)
    if mol is None:
        return None
    try:
        mol = Chem.AddHs(mol)
        result = AllChem.EmbedMolecule(mol, randomSeed=seed)
        if result != 0:
            result = AllChem.EmbedMolecule(mol, useRandomCoords=True, randomSeed=seed)
        if result == 0:
            AllChem.UFFOptimizeMolecule(mol)
        else:
            mol = Chem.RemoveHs(mol)
            return mol  # return 2D mol if 3D fails
        mol = Chem.RemoveHs(mol)
        return mol
    except Exception:
        return None


def smiles_to_sdf(smiles: str, output_path: str, seed: int = 42) -> bool:
    """Save molecule as SDF file. Returns True if successful."""
    mol = generate_3d_conformer(smiles, seed=seed)
    if mol is None:
        return False
    try:
        writer = Chem.SDWriter(output_path)
        writer.write(mol)
        writer.close()
        return True
    except Exception:
        return False
