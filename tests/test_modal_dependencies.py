import ast
import unittest
from pathlib import Path


MODAL_APP = Path(__file__).resolve().parents[1] / "modal_app.py"


class ModalDependencyDefinitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MODAL_APP.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_llm_secret_is_fixed_and_unconditional(self):
        self.assertNotIn("MODAL_LLM_SECRET_NAME", self.source)
        assignments = {
            node.targets[0].id: node.value
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        }
        secret = assignments["llm_secret"]
        self.assertIsInstance(secret, ast.Call)
        self.assertEqual(secret.args[0].value, "ai-drug-design-agent-llm")

    def test_fastapi_function_always_has_the_secret_dependency(self):
        fastapi_api = next(
            node
            for node in self.tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "fastapi_api"
        )
        app_function = next(
            decorator
            for decorator in fastapi_api.decorator_list
            if isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and decorator.func.attr == "function"
        )
        secrets = next(
            keyword.value
            for keyword in app_function.keywords
            if keyword.arg == "secrets"
        )
        self.assertIsInstance(secrets, ast.List)
        self.assertEqual(len(secrets.elts), 1)
        self.assertEqual(secrets.elts[0].id, "llm_secret")


if __name__ == "__main__":
    unittest.main()
