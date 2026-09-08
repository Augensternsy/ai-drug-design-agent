"""
Final Pre-Release Verification Script with Exact Filtering & Statistics Format
"""
import sys
import os
import time
import json
from pathlib import Path
from fastapi.testclient import TestClient

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from app.config import (
    MODEL_PATH, ESM2_PATH, SAMPLING_STEPS, CLAMP_MODE, DEVICE
)
from app.main import app

client = TestClient(app)

def run_verification():
    print("=" * 70)
    print("FINAL RE-VERIFICATION (STRICT RDKIT FILTERING & VINA RETRY)")
    print("=" * 70)

    gen_pass = False
    rdkit_pass = False
    vina_pass = False

    # 1. Test ESR1 num_samples=3, run_docking=false
    print("\n--- 1. ESR1 Generation (3 samples, no docking) ---")
    res1 = client.post("/api/generate", json={"target": "ESR1", "num_samples": 3, "run_docking": False})
    assert res1.status_code == 200
    task_id_1 = res1.json()["task_id"]

    start = time.time()
    task_1 = None
    while time.time() - start < 180:
        t_data = client.get(f"/api/tasks/{task_id_1}").json()
        if t_data["status"] == "completed":
            task_1 = t_data
            break
        elif t_data["status"] == "failed":
            raise RuntimeError(f"Task 1 failed: {t_data['error']}")
        time.sleep(2)

    stats_1_req = task_1["requested"]
    stats_1_gen = task_1["generated"]
    stats_1_val = task_1["valid"]
    stats_1_ret = task_1["returned"]
    cands_1 = task_1["candidates"]

    print(f"Stats: requested={stats_1_req} / generated={stats_1_gen} / valid={stats_1_val} / returned={stats_1_ret}")
    for c in cands_1:
        print(f"  Rank {c['rank']}: {c['smiles']} | QED={c['qed']} | Valid={c['valid']}")
        assert c["valid"] is True, "Invalid SMILES found in returned candidates!"

    if stats_1_ret > 0 and all(c["valid"] for c in cands_1):
        gen_pass = True
        rdkit_pass = True

    # 2. Test ESR1 num_samples=1, run_docking=true
    print("\n--- 2. ESR1 Generation & Docking (1 valid sample, run_docking=true) ---")
    res2 = client.post("/api/generate", json={"target": "ESR1", "num_samples": 1, "run_docking": True})
    assert res2.status_code == 200
    task_id_2 = res2.json()["task_id"]

    start = time.time()
    task_2 = None
    while time.time() - start < 180:
        t_data = client.get(f"/api/tasks/{task_id_2}").json()
        if t_data["status"] == "completed":
            task_2 = t_data
            break
        elif t_data["status"] == "failed":
            raise RuntimeError(f"Task 2 failed: {t_data['error']}")
        time.sleep(2)

    stats_2_req = task_2["requested"]
    stats_2_gen = task_2["generated"]
    stats_2_val = task_2["valid"]
    stats_2_ret = task_2["returned"]
    cands_2 = task_2["candidates"]

    print(f"Stats: requested={stats_2_req} / generated={stats_2_gen} / valid={stats_2_val} / returned={stats_2_ret}")
    for c in cands_2:
        print(f"  Rank {c['rank']}: {c['smiles']} | Vina={c['vina']} kcal/mol | QED={c['qed']}")
        assert c["valid"] is True, "Invalid SMILES found in returned candidates!"
        if c["vina"] is not None:
            vina_pass = True

    print("\n" + "=" * 70)
    print("FINAL REPORT SUMMARY")
    print("=" * 70)
    print(f"Generation: {'PASS' if gen_pass else 'FAIL'}")
    print(f"RDKit filtering: {'PASS' if rdkit_pass else 'FAIL'}")
    print(f"Vina: {'PASS' if vina_pass else 'FAIL'}")
    print(f"requested/generated/valid/returned: {stats_2_req}/{stats_2_gen}/{stats_2_val}/{stats_2_ret}")
    print(f"Final checkpoint: {MODEL_PATH}")
    print(f"Sampling steps: {SAMPLING_STEPS}")
    print(f"Clamp mode: {CLAMP_MODE}")
    print("=" * 70)

if __name__ == "__main__":
    run_verification()
