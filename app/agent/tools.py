"""Thin Agent Tool wrappers around the existing scientific services."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from app.config import DEMO_DATA_DIR, INFERENCE_MODE
from app.schemas.api_models import CandidateMolecule
from app.services.target_service import TargetRegistry


def resolve_target(target: str) -> str:
    """Resolve a user target to one of the 12 experimentally evaluated targets."""
    canonical = target.strip().upper()
    if canonical not in TargetRegistry.get_supported_targets():
        raise ValueError(f"Unsupported target: {target}")
    return canonical


def _load_demo_smiles(target: str, num_samples: int) -> list[str]:
    demo_csv = Path(DEMO_DATA_DIR) / f"generated_{target}.csv"
    if not demo_csv.exists():
        demo_csv = Path(DEMO_DATA_DIR) / "generated_ESR1.csv"
    smiles_list: list[str] = []
    if demo_csv.exists():
        with demo_csv.open("r", encoding="utf-8") as stream:
            reader = csv.reader(stream)
            next(reader, None)
            for row in reader:
                if row and row[0] != "INVALID":
                    smiles_list.append(row[0])
                    if len(smiles_list) >= num_samples:
                        break
    return smiles_list or [
        "COc1ccc(C(=O)OC[C@H]2CC[C@H](NS(=O)(=O)c3cccc(OC)n3)CC2)cc1",
        "CNC(=O)c1ccc2cc(NC)nc(Nc3cccc(Cl)c3C(N)=O)c2n1",
        "CN1CC(NC(=O)c2cc(-c3cccnc3CC(F)(F)F)nc(N)n2)C1",
    ][:num_samples]


def generate_molecules(target: str, num_samples: int) -> list[str]:
    """Delegate generation to the existing demo or DLPS-E2PO model service."""
    canonical = resolve_target(target)
    if INFERENCE_MODE.lower() == "demo":
        return _load_demo_smiles(canonical, num_samples)
    from app.services.model_service import generate_molecules_for_target

    return generate_molecules_for_target(canonical, num_samples)


def evaluate_properties(smiles: str) -> dict:
    """Delegate molecular property calculation to the existing RDKit evaluator."""
    from app.services.eval_service import evaluate_smiles

    return evaluate_smiles(smiles)


def molecular_docking(target: str, smiles_list: list[str]) -> list[dict]:
    """Delegate docking to the existing AutoDock Vina service without altering it."""
    from app.services.docking_service import dock_molecules, is_docking_available

    if not is_docking_available():
        raise RuntimeError("AutoDock Vina or Meeko is unavailable in this runtime")
    return dock_molecules(resolve_target(target), smiles_list)


def rank_candidates(
    candidates: Iterable[CandidateMolecule], run_docking: bool
) -> list[CandidateMolecule]:
    """Rank by Vina when requested; otherwise rank by QED."""
    ranked = list(candidates)
    if run_docking and any(item.vina is not None for item in ranked):
        ranked.sort(key=lambda item: item.vina if item.vina is not None else 999.0)
    else:
        ranked.sort(key=lambda item: item.qed if item.qed is not None else -1.0, reverse=True)
    for index, candidate in enumerate(ranked, start=1):
        candidate.rank = index
    return ranked


def attach_molecular_assets(candidate: CandidateMolecule) -> CandidateMolecule:
    """Attach free RDKit-generated 2D SVG and 3D SDF payloads."""
    from app.services.rdkit_service import smiles_to_2d_svg, smiles_to_sdf_block

    candidate.structure_svg = smiles_to_2d_svg(candidate.smiles)
    candidate.sdf = smiles_to_sdf_block(candidate.smiles)
    return candidate


def summarize_results(target: str, candidates: list[CandidateMolecule], docked: bool) -> str:
    if not candidates:
        return f"{target} 任务完成，但没有候选分子通过当前筛选条件。"
    best = candidates[0]
    summary = (
        f"{target} 任务完成，共返回 {len(candidates)} 个 RDKit 有效候选分子；"
        f"排名第一的 QED={best.qed if best.qed is not None else 'N/A'}，"
        f"SA={best.sa if best.sa is not None else 'N/A'}。"
    )
    if docked:
        summary += (
            f" Vina score={best.vina:.2f} kcal/mol。"
            if best.vina is not None
            else " Vina 未返回有效评分，请查看任务错误信息。"
        )
    return summary
