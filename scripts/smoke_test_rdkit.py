"""
Smoke Test: RDKit Property Calculation

验证：
  从 smoke_test/ESR1_generated.csv 读取分子，计算：
  - Validity, QED, SA, MolWt, LogP, Ro5

用法：
  python scripts/smoke_test_rdkit.py [--target ESR1]
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
    parser = argparse.ArgumentParser(description="Smoke test: RDKit property calculation")
    parser.add_argument("--target", type=str, default="ESR1")
    parser.add_argument("--input_csv", type=str, default=None,
                        help="Path to CSV with SMILES column (default: smoke_test/{target}_generated.csv)")
    args = parser.parse_args()

    from app.config import SMOKE_TEST_DIR
    from app.services.rdkit_service import compute_all_properties, calculate_dataset_metrics

    input_csv = args.input_csv
    if input_csv is None:
        input_csv = os.path.join(SMOKE_TEST_DIR, f"{args.target}_generated.csv")

    if not os.path.exists(input_csv):
        print(f"ERROR: Input CSV not found: {input_csv}")
        print("Run smoke_test_generation.py first.")
        sys.exit(1)

    # Read SMILES
    smiles_list = []
    with open(input_csv, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            smiles_list.append(row["SMILES"])

    print("=" * 60)
    print(f"Smoke Test: RDKit Properties")
    print(f"  Target:  {args.target}")
    print(f"  Input:   {input_csv}")
    print(f"  Count:   {len(smiles_list)} molecules")
    print("=" * 60)

    # Per-molecule properties
    print("\nPer-molecule properties:")
    print(f"{'#':<4} {'SMILES':<45} {'QED':<6} {'SA':<6} {'MolWt':<8} {'LogP':<6} {'Ro5'}")
    print("-" * 85)

    for i, smi in enumerate(smiles_list):
        props = compute_all_properties(smi)
        if props["valid"]:
            qed_str = f"{props['qed']:.3f}" if props['qed'] else "N/A"
            sa_str = f"{props['sa']:.2f}" if props['sa'] else "N/A"
            mw_str = f"{props['mol_wt']:.1f}" if props['mol_wt'] else "N/A"
            logp_str = f"{props['log_p']:.2f}" if props['log_p'] else "N/A"
            ro5_str = "✓" if props["ro5"] else "✗"
            display_smi = smi[:42] + "..." if len(smi) > 45 else smi
            print(f"{i+1:<4} {display_smi:<45} {qed_str:<6} {sa_str:<6} {mw_str:<8} {logp_str:<6} {ro5_str}")
        else:
            display_smi = smi[:42] + "..." if len(smi) > 45 else smi
            print(f"{i+1:<4} {display_smi:<45} INVALID")

    # Dataset metrics
    print("\nDataset-level metrics:")
    metrics = calculate_dataset_metrics(smiles_list, args.target)
    for k, v in metrics.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")
        else:
            print(f"  {k}: {v}")

    if metrics["n_valid"] > 0:
        print(f"\n✅ RDKit smoke test PASSED ({metrics['n_valid']} valid molecules)")
        sys.exit(0)
    else:
        print("\n⚠️  WARNING: No valid molecules to evaluate!")
        sys.exit(1)


if __name__ == "__main__":
    main()
