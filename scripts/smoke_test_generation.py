"""
Smoke Test: Generation Pipeline

验证：
  1. 加载 ESM-2（本地）
  2. 读取 ESR1 蛋白序列
  3. 加载 direct_ki_e2po_15k.pt
  4. 完成完整 diffusion sampling (200 steps, NoClamp)
  5. decode SMILES
  6. RDKit 检查 validity
  7. 输出 outputs/smoke_test/ESR1_generated.csv

用法：
  python scripts/smoke_test_generation.py [--num_samples 3] [--target ESR1]
"""

import sys
import os
import argparse
import csv
import time

# ── 确保项目根目录在 Python 路径中 ──────────────────────────────────────────────
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(description="Smoke test: molecule generation")
    parser.add_argument("--target", type=str, default="ESR1")
    parser.add_argument("--num_samples", type=int, default=3)
    parser.add_argument("--model", type=str, default="e2po",
                        choices=["e2po", "base"])
    args = parser.parse_args()

    print("=" * 60)
    print(f"Smoke Test: Generation")
    print(f"  Target:      {args.target}")
    print(f"  Num samples: {args.num_samples}")
    print(f"  Model:       {args.model}")
    print("=" * 60)

    t_start = time.time()

    from app.services.generation_service import generate_molecules
    from app.config import SMOKE_TEST_DIR

    results = generate_molecules(
        target=args.target,
        num_samples=args.num_samples,
        model_name=args.model,
        batch_size=min(args.num_samples, 5),
    )

    os.makedirs(SMOKE_TEST_DIR, exist_ok=True)
    output_csv = os.path.join(SMOKE_TEST_DIR, f"{args.target}_generated.csv")

    with open(output_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["SMILES", "Valid"])
        for r in results:
            writer.writerow([r["smiles"], r["valid"]])

    elapsed = time.time() - t_start
    valid_count = sum(1 for r in results if r["valid"])

    print("\n" + "=" * 60)
    print("SMOKE TEST RESULTS:")
    print(f"  Total generated:  {len(results)}")
    print(f"  Valid SMILES:     {valid_count} / {len(results)}")
    print(f"  Time elapsed:     {elapsed:.1f}s")
    print(f"  Output saved to:  {output_csv}")
    print("=" * 60)
    print("\nGenerated SMILES:")
    for i, r in enumerate(results):
        status = "✓ VALID" if r["valid"] else "✗ INVALID"
        print(f"  [{i+1}] {status} | {r['smiles']}")

    if valid_count == 0:
        print("\n⚠️  WARNING: No valid molecules generated!")
        sys.exit(1)
    else:
        print(f"\n✅ Smoke test PASSED ({valid_count}/{len(results)} valid)")
        sys.exit(0)


if __name__ == "__main__":
    main()
