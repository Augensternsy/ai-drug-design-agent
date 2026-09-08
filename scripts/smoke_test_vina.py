"""
Smoke Test: Vina Docking

验证：
  从 smoke_test/ESR1_generated.csv 中取第一个有效分子，对 ESR1 执行 Vina 对接。

用法：
  python scripts/smoke_test_vina.py [--target ESR1]
"""

import sys
import os
import argparse
import csv

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_SCRIPT_DIR)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main():
    parser = argparse.ArgumentParser(description="Smoke test: Vina docking")
    parser.add_argument("--target", type=str, default="ESR1")
    parser.add_argument("--smiles", type=str, default=None,
                        help="SMILES to dock (default: read from smoke_test CSV)")
    args = parser.parse_args()

    from app.config import SMOKE_TEST_DIR
    from app.services.docking_service import (
        is_docking_available, dock_molecules, dock_single,
        get_receptor_path, get_ligand_ref_path, compute_docking_box
    )

    print("=" * 60)
    print(f"Smoke Test: Vina Docking")
    print(f"  Target: {args.target}")
    print("=" * 60)

    if not is_docking_available():
        print("\n⚠️  Vina or Meeko not available.")
        print("To enable docking: pip install vina meeko")
        print("See DEPENDENCIES.md for details.")
        sys.exit(2)  # exit code 2 = skipped (not failure)

    # Get SMILES
    test_smiles = args.smiles
    if test_smiles is None:
        input_csv = os.path.join(SMOKE_TEST_DIR, f"{args.target}_generated.csv")
        if not os.path.exists(input_csv):
            print(f"ERROR: No input CSV found at {input_csv}")
            print("Run smoke_test_generation.py first, or provide --smiles")
            sys.exit(1)

        with open(input_csv, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Valid", "").lower() in ("true", "1"):
                    test_smiles = row["SMILES"]
                    break

    if test_smiles is None:
        print("ERROR: No valid SMILES found.")
        sys.exit(1)

    print(f"\nTest SMILES: {test_smiles}")

    # Check receptor
    receptor_path = get_receptor_path(args.target)
    if not receptor_path:
        print(f"ERROR: Receptor PDBQT not found for {args.target}")
        sys.exit(1)
    print(f"Receptor: {receptor_path}")

    # Compute box
    ref_lig = get_ligand_ref_path(args.target)
    center, box_size = compute_docking_box(ref_lig)
    print(f"Box center: {center}")
    print(f"Box size:   {box_size}")

    # Run docking
    print("\nRunning Vina docking...")
    result = dock_single(test_smiles, receptor_path, center, box_size)

    print("\n" + "=" * 60)
    print("DOCKING RESULT:")
    print(f"  SMILES:     {result['smiles']}")
    print(f"  Vina Score: {result['vina_score']}")
    print(f"  Success:    {result['success']}")
    if 'error' in result:
        print(f"  Error:      {result['error']}")
    print("=" * 60)

    if result["success"] and result["vina_score"] is not None:
        print(f"\n✅ Vina smoke test PASSED! Score: {result['vina_score']:.2f} kcal/mol")
        sys.exit(0)
    else:
        print("\n⚠️  Vina docking failed or returned no score.")
        sys.exit(1)


if __name__ == "__main__":
    main()
