"""
Automated Integration Test Suite for FastAPI Drug Design Backend
Tests:
  1. GET /api/health
  2. GET /api/targets
  3. POST /api/generate (ESR1, num_samples=3, run_docking=false)
  4. POST /api/generate (ESR1, num_samples=1, run_docking=true)
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

from app.main import app

client = TestClient(app)

def run_tests():
    print("=" * 70)
    print("RUNNING API INTEGRATION TESTS")
    print("=" * 70)

    # 1. Test GET /api/health
    print("\n[TEST 1] GET /api/health")
    res1 = client.get("/api/health")
    assert res1.status_code == 200, f"Health check failed: {res1.text}"
    health_data = res1.json()
    print("Health Data:", json.dumps(health_data, indent=2))
    assert health_data["status"] == "ok"
    assert health_data["cuda_available"] is True, "CUDA is not available!"

    # 2. Test GET /api/targets
    print("\n[TEST 2] GET /api/targets")
    res2 = client.get("/api/targets")
    assert res2.status_code == 200, f"Targets check failed: {res2.text}"
    targets_data = res2.json()
    print(f"Supported Targets ({len(targets_data['targets'])}):", [t["target"] for t in targets_data["targets"]])
    assert len(targets_data["targets"]) == 12

    # 3. Test POST /api/generate without docking
    print("\n[TEST 3] POST /api/generate (ESR1, num_samples=3, run_docking=false)")
    req_body_1 = {
        "target": "ESR1",
        "num_samples": 3,
        "run_docking": False
    }
    res3 = client.post("/api/generate", json=req_body_1)
    assert res3.status_code == 200, f"Generate request failed: {res3.text}"
    gen_data_1 = res3.json()
    task_id_1 = gen_data_1["task_id"]
    print(f"Task 1 Created: ID={task_id_1}, Status={gen_data_1['status']}")

    # Poll status until completed
    max_wait = 180
    start_time = time.time()
    task_result_1 = None

    while time.time() - start_time < max_wait:
        res_status = client.get(f"/api/tasks/{task_id_1}")
        assert res_status.status_code == 200
        task_data = res_status.json()
        print(f"  Task 1 Status: {task_data['status']} | Progress: {task_data['progress']}% | Stage: {task_data['current_stage']}")
        if task_data["status"] == "completed":
            task_result_1 = task_data
            break
        elif task_data["status"] == "failed":
            raise RuntimeError(f"Task 1 failed: {task_data['error']}")
        time.sleep(2)

    assert task_result_1 is not None, "Task 1 timed out!"
    print("\nTask 1 Final Result Candidates:")
    for cand in task_result_1["candidates"]:
        print(f"  [{cand['rank']}] {cand['smiles']} | QED={cand['qed']}, SA={cand['sa']}, Lipinski={cand['lipinski']}")

    assert len(task_result_1["candidates"]) > 0, "No candidates returned!"

    # 4. Test POST /api/generate with Vina docking
    print("\n[TEST 4] POST /api/generate (ESR1, num_samples=3, run_docking=true)")
    req_body_2 = {
        "target": "ESR1",
        "num_samples": 3,
        "run_docking": True
    }
    res4 = client.post("/api/generate", json=req_body_2)
    assert res4.status_code == 200, f"Generate request with docking failed: {res4.text}"
    gen_data_2 = res4.json()
    task_id_2 = gen_data_2["task_id"]
    print(f"Task 2 Created: ID={task_id_2}, Status={gen_data_2['status']}")

    start_time = time.time()
    task_result_2 = None

    while time.time() - start_time < max_wait:
        res_status = client.get(f"/api/tasks/{task_id_2}")
        assert res_status.status_code == 200
        task_data = res_status.json()
        print(f"  Task 2 Status: {task_data['status']} | Progress: {task_data['progress']}% | Stage: {task_data['current_stage']}")
        if task_data["status"] == "completed":
            task_result_2 = task_data
            break
        elif task_data["status"] == "failed":
            raise RuntimeError(f"Task 2 failed: {task_data['error']}")
        time.sleep(2)

    assert task_result_2 is not None, "Task 2 timed out!"
    print("\nTask 2 Final Result Candidate with Vina Docking:")
    for cand in task_result_2["candidates"]:
        print(f"  [{cand['rank']}] {cand['smiles']} | Vina={cand['vina']} kcal/mol | QED={cand['qed']}")
    has_vina = any(cand["vina"] is not None for cand in task_result_2["candidates"])
    assert has_vina, "No candidate received a Vina docking score!"

    print("\n" + "=" * 70)
    print("ALL API INTEGRATION TESTS PASSED SUCCESSFULLY! 🎉")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
