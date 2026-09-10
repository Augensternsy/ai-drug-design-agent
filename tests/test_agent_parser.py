import unittest

from app.agent.parser import AgentParseError, parse_rule_prompt


class AgentParserTests(unittest.TestCase):
    def test_parses_chinese_workflow_request(self):
        plan = parse_rule_prompt(
            "帮我针对 ESR1 生成 5 个候选分子，QED 优先，SA<3.5，并对最优结果进行 Vina 对接。"
        )
        self.assertEqual(plan.target, "ESR1")
        self.assertEqual(plan.num_samples, 5)
        self.assertEqual(plan.sa_threshold, 3.5)
        self.assertTrue(plan.qed_priority)
        self.assertTrue(plan.run_docking)
        self.assertEqual(plan.dock_top_k, 1)
        self.assertEqual(plan.parser, "rules")

    def test_rejects_request_above_public_limit(self):
        with self.assertRaisesRegex(AgentParseError, "1–5"):
            parse_rule_prompt("针对 JAK1 生成 8 个候选分子")

    def test_requires_verified_target(self):
        with self.assertRaisesRegex(AgentParseError, "未识别到已验证靶点"):
            parse_rule_prompt("帮我生成 3 个候选分子")

    def test_explicit_no_docking_wins(self):
        plan = parse_rule_prompt("针对 FTO 生成 2 个分子，不要进行 Vina 对接")
        self.assertFalse(plan.run_docking)


if __name__ == "__main__":
    unittest.main()
