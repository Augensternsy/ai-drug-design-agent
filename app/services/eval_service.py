"""
RDKit Evaluation Service — Computes QED, SA score, LogP, Molecular Weight, and Lipinski Rule of 5.
"""
import sys
import os
import logging
from typing import Dict, Any, Optional

from rdkit import Chem, RDLogger
from rdkit.Chem import Descriptors, QED, rdMolDescriptors
RDLogger.DisableLog("rdApp.*")

logger = logging.getLogger(__name__)

# Try importing SAScorer from source_backup or rdkit
_sa_scorer = None
try:
    _project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _source_backup = os.path.join(_project_root, "source_backup")
    if _source_backup not in sys.path:
        sys.path.insert(0, _source_backup)
    
    # Try SAScorer from improved_diffusion or sascorer.py
    import sascorer
    _sa_scorer = sascorer.calculateScore
except Exception:
    try:
        from rdkit.Chem import RDConfig
        sys.path.append(os.path.join(RDConfig.RDContribDir, 'SA_Score'))
        import sascorer
        _sa_scorer = sascorer.calculateScore
    except Exception:
        logger.warning("sascorer module not found. SA score will fall back to estimation.")


def calculate_sa_score(mol: Chem.Mol) -> float:
    """Calculate Synthetic Accessibility (SA) Score (1=easy, 10=hard)."""
    if _sa_scorer is not None:
        try:
            return float(_sa_scorer(mol))
        except Exception:
            pass
    
    # Fallback SA score calculation based on complexity metrics
    num_rings = rdMolDescriptors.CalcNumRings(mol)
    num_chiral = len(Chem.FindMolChiralCenters(mol, includeUnassigned=True))
    mol_wt = Descriptors.MolWt(mol)
    score = 1.0 + (num_rings * 0.5) + (num_chiral * 0.3) + (mol_wt / 150.0)
    return float(min(max(score, 1.0), 10.0))


def check_lipinski(mol: Chem.Mol) -> bool:
    """
    Check Lipinski Rule of 5:
    - MolWt <= 500
    - LogP <= 5.0
    - H-bond Donors (HBD) <= 5
    - H-bond Acceptors (HBA) <= 10
    Max 1 violation allowed.
    """
    mol_wt = Descriptors.MolWt(mol)
    logp = Descriptors.MolLogP(mol)
    hbd = rdMolDescriptors.CalcNumHBD(mol)
    hba = rdMolDescriptors.CalcNumHBA(mol)

    violations = 0
    if mol_wt > 500:
        violations += 1
    if logp > 5.0:
        violations += 1
    if hbd > 5:
        violations += 1
    if hba > 10:
        violations += 1

    return violations <= 1


def render_smiles_to_svg(smiles: str, width: int = 300, height: int = 200) -> Optional[str]:
    """Render 2D molecular structure to SVG string using RDKit."""
    if not smiles or smiles in ("INVALID", "nan", ""):
        return None
    try:
        from rdkit.Chem import AllChem
        from rdkit.Chem.Draw import rdMolDraw2D

        mol = Chem.MolFromSmiles(smiles.strip())
        if mol is None:
            return None

        AllChem.Compute2DCoords(mol)
        drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
        drawer.DrawMolecule(mol)
        drawer.FinishDrawing()
        return drawer.GetDrawingText()
    except Exception as e:
        logger.warning(f"Failed to render 2D SVG for SMILES '{smiles}': {e}")
        return None


def generate_3d_mol_block(smiles: str) -> Optional[str]:
    """
    Generate 3D molecular conformer MolBlock string using RDKit:
    SMILES -> AddHs -> EmbedMolecule -> MMFFOptimizeMolecule -> MolToMolBlock
    """
    if not smiles or smiles in ("INVALID", "nan", ""):
        return None
    try:
        from rdkit.Chem import AllChem

        mol = Chem.MolFromSmiles(smiles.strip())
        if mol is None:
            return None

        mol_h = Chem.AddHs(mol)
        embed_res = AllChem.EmbedMolecule(mol_h, randomSeed=42)
        if embed_res != 0:
            embed_res = AllChem.EmbedMolecule(mol_h, useRandomCoordinates=True)

        try:
            if AllChem.MMFFHasAllMoleculeParams(mol_h):
                AllChem.MMFFOptimizeMolecule(mol_h)
            else:
                AllChem.UFFOptimizeMolecule(mol_h)
        except Exception as opt_err:
            logger.debug(f"3D MMFF/UFF optimization warning for SMILES '{smiles}': {opt_err}")

        return Chem.MolToMolBlock(mol_h)
    except Exception as e:
        logger.warning(f"Failed to generate 3D MolBlock for SMILES '{smiles}': {e}")
        return None


def evaluate_smiles(smiles: str) -> Dict[str, Any]:
    """
    Evaluate a single SMILES string.
    
    Returns dict:
        valid: bool
        smiles: str
        qed: float (0..1)
        sa: float (1..10)
        molwt: float
        logp: float
        lipinski: bool
        molecule_svg: str | None
        mol_block: str | None
    """
    if not smiles or smiles == "INVALID":
        return {
            "valid": False,
            "smiles": smiles,
            "qed": None,
            "sa": None,
            "molwt": None,
            "logp": None,
            "lipinski": False,
            "molecule_svg": None,
            "mol_block": None
        }

    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return {
                "valid": False,
                "smiles": smiles,
                "qed": None,
                "sa": None,
                "molwt": None,
                "logp": None,
                "lipinski": False,
                "molecule_svg": None,
                "mol_block": None
            }

        qed_val = float(QED.qed(mol))
        sa_val = calculate_sa_score(mol)
        molwt_val = float(Descriptors.MolWt(mol))
        logp_val = float(Descriptors.MolLogP(mol))
        lipinski_val = check_lipinski(mol)
        svg_val = render_smiles_to_svg(smiles)
        mol_block_val = generate_3d_mol_block(smiles)

        return {
            "valid": True,
            "smiles": smiles,
            "qed": round(qed_val, 4),
            "sa": round(sa_val, 4),
            "molwt": round(molwt_val, 2),
            "logp": round(logp_val, 2),
            "lipinski": lipinski_val,
            "molecule_svg": svg_val,
            "mol_block": mol_block_val
        }

    except Exception as e:
        logger.warning(f"Failed to evaluate SMILES '{smiles}': {e}")
        return {
            "valid": False,
            "smiles": smiles,
            "qed": None,
            "sa": None,
            "molwt": None,
            "logp": None,
            "lipinski": False,
            "molecule_svg": None,
            "mol_block": None
        }
