"""
Async Task Service — Manages generation tasks, auto-retry for valid molecules, and background execution lifecycle.
"""
import os
import uuid
import asyncio
import logging
from typing import Dict, Optional, List, Any
from pathlib import Path

from app.schemas.api_models import TaskStatusResponse, CandidateMolecule, GenerateRequest
from app.services.target_service import TargetRegistry
from app.services.eval_service import evaluate_smiles
from app.services.docking_service import is_docking_available, dock_molecules, get_receptor_path, get_ligand_ref_path, compute_docking_box
from app.config import INFERENCE_MODE, DEMO_DATA_DIR

logger = logging.getLogger(__name__)

# Global in-memory task store
_TASKS: Dict[str, Dict[str, Any]] = {}


class TaskService:
    """Service to create, query, and run asynchronous molecule generation tasks."""

    @staticmethod
    def create_task(req: GenerateRequest, background_tasks: Any = None) -> str:
        task_id = str(uuid.uuid4())
        _TASKS[task_id] = {
            "task_id": task_id,
            "target": req.target.upper(),
            "num_samples": req.num_samples,
            "qed_threshold": req.qed_threshold,
            "sa_threshold": req.sa_threshold,
            "run_docking": req.run_docking,
            "status": "queued",
            "progress": 0.0,
            "current_stage": "Task queued",
            "error": None,
            "requested": req.num_samples,
            "generated": 0,
            "valid": 0,
            "returned": 0,
            "candidates": []
        }
        if background_tasks is not None:
            background_tasks.add_task(TaskService._run_generation_task_sync, task_id)
        else:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(TaskService._run_generation_task(task_id))
            except RuntimeError:
                import threading
                threading.Thread(target=lambda: asyncio.run(TaskService._run_generation_task(task_id)), daemon=True).start()
        return task_id

    @staticmethod
    def _run_generation_task_sync(task_id: str):
        asyncio.run(TaskService._run_generation_task(task_id))

    @staticmethod
    def get_task(task_id: str) -> Optional[TaskStatusResponse]:
        if task_id not in _TASKS:
            return None
        t = _TASKS[task_id]
        return TaskStatusResponse(
            task_id=t["task_id"],
            target=t["target"],
            status=t["status"],
            progress=t["progress"],
            current_stage=t["current_stage"],
            error=t["error"],
            num_samples=t["num_samples"],
            requested=t.get("requested", t["num_samples"]),
            generated=t.get("generated", 0),
            valid=t.get("valid", 0),
            returned=t.get("returned", len(t.get("candidates", []))),
            candidates=t["candidates"]
        )

    @staticmethod
    async def _run_generation_task(task_id: str):
        t = _TASKS.get(task_id)
        if not t:
            return

        target = t["target"]
        num_samples = t["num_samples"]
        run_docking = t["run_docking"]

        try:
            # Stage 1: Loading
            t["status"] = "loading"
            t["progress"] = 10.0
            t["current_stage"] = f"Loading model and sequence for target {target}..."
            await asyncio.sleep(0.5)

            # Stage 2: Encoding
            t["status"] = "encoding"
            t["progress"] = 25.0
            t["current_stage"] = f"Encoding protein sequence with ESM-2..."
            await asyncio.sleep(0.5)

            # Stage 3 & 4: Generating & Evaluating with Auto-Retry for RDKit Valid molecules
            t["status"] = "generating"
            t["progress"] = 40.0
            t["current_stage"] = f"Generating candidate molecules for target {target}..."

            valid_candidates: List[CandidateMolecule] = []
            total_generated = 0
            max_attempts = 3
            attempt = 0

            while len(valid_candidates) < num_samples and attempt < max_attempts:
                attempt += 1
                needed = num_samples - len(valid_candidates)
                batch_to_gen = max(needed, 2) if attempt > 1 else num_samples

                if INFERENCE_MODE.lower() == "demo":
                    batch_smiles = TaskService._load_demo_smiles(target, batch_to_gen)
                    await asyncio.sleep(0.5)
                else:
                    from app.services.model_service import generate_molecules_for_target
                    batch_smiles = await asyncio.to_thread(
                        generate_molecules_for_target, target, batch_to_gen
                    )

                total_generated += len(batch_smiles)

                for smiles in batch_smiles:
                    eval_res = evaluate_smiles(smiles)
                    # STRICT RULE: RDKit Invalid molecules MUST NOT enter final candidates
                    if not eval_res["valid"]:
                        continue

                    if t["qed_threshold"] and (eval_res["qed"] or 0) < t["qed_threshold"]:
                        continue
                    if t["sa_threshold"] and (eval_res["sa"] or 10) > t["sa_threshold"]:
                        continue

                    # Avoid duplicate SMILES
                    if any(c.smiles == smiles for c in valid_candidates):
                        continue

                    candidate = CandidateMolecule(
                        rank=len(valid_candidates) + 1,
                        smiles=smiles,
                        valid=True,
                        qed=eval_res.get("qed"),
                        sa=eval_res.get("sa"),
                        molwt=eval_res.get("molwt"),
                        logp=eval_res.get("logp"),
                        lipinski=eval_res.get("lipinski"),
                        vina=None
                    )
                    valid_candidates.append(candidate)
                    if len(valid_candidates) >= num_samples:
                        break

            evaluated_candidates = valid_candidates[:num_samples]
            t["generated"] = total_generated
            t["valid"] = len(evaluated_candidates)

            # Stage 5: Docking (optional, ONLY valid molecules allowed)
            if run_docking and is_docking_available() and evaluated_candidates:
                t["status"] = "docking"
                t["progress"] = 80.0
                t["current_stage"] = f"Performing AutoDock Vina molecular docking..."

                receptor_path = TargetRegistry.get_receptor_path(target)
                ref_ligand = TargetRegistry.get_reference_ligand_path(target)

                if receptor_path and ref_ligand:
                    center, box_size = compute_docking_box(str(ref_ligand))
                    valid_smiles = [c.smiles for c in evaluated_candidates]

                    dock_results = await asyncio.to_thread(
                        dock_molecules, valid_smiles, str(receptor_path), center, box_size
                    )
                    dock_map = {res["smiles"]: res.get("vina_score") for res in dock_results}

                    for cand in evaluated_candidates:
                        if cand.smiles in dock_map:
                            cand.vina = dock_map[cand.smiles]

            # Stage 6: Ranking
            t["status"] = "ranking"
            t["progress"] = 95.0
            t["current_stage"] = f"Ranking candidate molecules..."

            if run_docking:
                evaluated_candidates.sort(key=lambda c: (c.vina if c.vina is not None else 999.0))
            else:
                evaluated_candidates.sort(key=lambda c: (c.qed if c.qed is not None else -1.0), reverse=True)

            for rank, cand in enumerate(evaluated_candidates, start=1):
                cand.rank = rank

            # Stage 7: Completed
            t["candidates"] = evaluated_candidates
            t["returned"] = len(evaluated_candidates)
            t["status"] = "completed"
            t["progress"] = 100.0
            t["current_stage"] = f"Generation and evaluation completed successfully! ({len(evaluated_candidates)} valid candidates returned)"

        except Exception as e:
            logger.exception(f"Task {task_id} failed with error")
            t["status"] = "failed"
            t["progress"] = 100.0
            t["current_stage"] = f"Task failed"
            t["error"] = str(e)

    @staticmethod
    def _load_demo_smiles(target: str, num_samples: int) -> List[str]:
        """Load real pre-generated SMILES from demo_data directory."""
        demo_csv = Path(DEMO_DATA_DIR) / f"generated_{target}.csv"
        if not demo_csv.exists():
            demo_csv = Path(DEMO_DATA_DIR) / "generated_ESR1.csv"

        smiles_list = []
        if demo_csv.exists():
            import csv
            with open(demo_csv, "r") as f:
                reader = csv.reader(f)
                header = next(reader, None)
                for row in reader:
                    if row and row[0] != "INVALID":
                        smiles_list.append(row[0])
                        if len(smiles_list) >= num_samples:
                            break

        if not smiles_list:
            smiles_list = [
                "COc1ccc(C(=O)OC[C@H]2CC[C@H](NS(=O)(=O)c3cccc(OC)n3)CC2)cc1",
                "CNC(=O)c1ccc2cc(NC)nc(Nc3cccc(Cl)c3C(N)=O)c2n1",
                "CN1CC(NC(=O)c2cc(-c3cccnc3CC(F)(F)F)nc(N)n2)C1"
            ][:num_samples]

        return smiles_list
