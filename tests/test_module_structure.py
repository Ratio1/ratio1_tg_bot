import ast
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
BOT_FILE = REPO_ROOT / "ratio1_tg_bot.py"


class ModuleStructureTests(unittest.TestCase):
  def test_bot_specific_logic_stays_inside_ratio1_handlers(self):
    tree = ast.parse(BOT_FILE.read_text())
    allowed_top_level_functions = {"loop_processing", "reply"}
    allowed_assignment_names = set()

    for node in tree.body:
      if isinstance(node, (ast.Import, ast.ImportFrom)):
        continue
      if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
        continue
      if isinstance(node, ast.FunctionDef):
        self.assertIn(node.name, allowed_top_level_functions)
        continue
      if isinstance(node, ast.Try):
        continue
      if isinstance(node, ast.Assign):
        assigned_names = {
          target.id
          for target in node.targets
          if isinstance(target, ast.Name)
        }
        self.assertTrue(
          assigned_names <= allowed_assignment_names,
          f"Unexpected module-level assignment: {sorted(assigned_names)}",
        )
        continue
      if isinstance(node, ast.If) and isinstance(node.test, ast.Compare):
        left = node.test.left
        comparators = node.test.comparators
        if (
          isinstance(left, ast.Name)
          and left.id == "__name__"
          and len(comparators) == 1
          and isinstance(comparators[0], ast.Constant)
          and comparators[0].value == "__main__"
        ):
          continue

      self.fail(f"Unexpected module-level node: {ast.dump(node, include_attributes=False)}")


if __name__ == "__main__":
  unittest.main()
