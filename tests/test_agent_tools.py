import unittest

from app.agent.tools import rank_candidates, resolve_target, summarize_results
from app.schemas.api_models import CandidateMolecule


class AgentToolTests(unittest.TestCase):
    def test_resolve_target_rejects_unknown_target(self):
        with self.assertRaisesRegex(ValueError, "Unsupported target"):
            resolve_target("UNKNOWN")

    def test_rank_candidates_by_qed_without_docking(self):
        candidates = [
            CandidateMolecule(rank=1, smiles="CC", qed=0.2),
            CandidateMolecule(rank=2, smiles="CCC", qed=0.8),
        ]
        ranked = rank_candidates(candidates, run_docking=False)
        self.assertEqual([item.smiles for item in ranked], ["CCC", "CC"])
        self.assertEqual([item.rank for item in ranked], [1, 2])

    def test_rank_candidates_by_vina_when_requested(self):
        candidates = [
            CandidateMolecule(rank=1, smiles="CC", vina=-6.1),
            CandidateMolecule(rank=2, smiles="CCC", vina=-8.4),
        ]
        ranked = rank_candidates(candidates, run_docking=True)
        self.assertEqual(ranked[0].smiles, "CCC")
        self.assertIn("Vina score=-8.40", summarize_results("ESR1", ranked, True))


if __name__ == "__main__":
    unittest.main()
