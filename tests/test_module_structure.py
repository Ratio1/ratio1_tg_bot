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

  def test_ratio1_handlers_do_not_import_dependencies_locally(self):
    tree = ast.parse(BOT_FILE.read_text())
    handler_names = {"loop_processing", "reply"}
    handlers = [
      node
      for node in tree.body
      if isinstance(node, ast.FunctionDef) and node.name in handler_names
    ]

    self.assertEqual({handler.name for handler in handlers}, handler_names)
    for handler in handlers:
      local_imports = [
        node
        for node in ast.walk(handler)
        if isinstance(node, (ast.Import, ast.ImportFrom))
      ]
      self.assertEqual(
        local_imports,
        [],
        f"{handler.name} should not use local imports because Ratio1 serializes handlers as remote code.",
      )

  def test_reply_uses_ratio1_plugin_url_helpers(self):
    tree = ast.parse(BOT_FILE.read_text())
    reply = next(
      node
      for node in tree.body
      if isinstance(node, ast.FunctionDef) and node.name == "reply"
    )
    plugin_attrs = {
      node.attr
      for node in ast.walk(reply)
      if isinstance(node, ast.Attribute)
      and isinstance(node.value, ast.Name)
      and node.value.id == "plugin"
    }

    self.assertIn("urlparse", plugin_attrs)
    self.assertIn("urlunparse", plugin_attrs)


if __name__ == "__main__":
  unittest.main()
