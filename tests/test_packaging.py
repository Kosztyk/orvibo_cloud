"""Packaging tests, not hardware or Home Assistant runtime tests."""

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "orvibo_packaging", ROOT / "tools/check_repository.py"
)
assert spec and spec.loader
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PackagingTests(unittest.TestCase):
    def test_repository_layout(self):
        self.assertEqual(checker.inspect_repository(ROOT), [])

    def test_manifest_metadata(self):
        m = json.loads(
            (ROOT / "custom_components/orvibo_cloud/manifest.json").read_text()
        )
        self.assertEqual(m["domain"], "orvibo_cloud")
        self.assertEqual(m["version"], "1.3.2")
        self.assertEqual(m["integration_type"], "hub")

    def test_hacs_metadata(self):
        h = json.loads((ROOT / "hacs.json").read_text())
        self.assertEqual(h["name"], "ORVIBO Cloud")
        self.assertTrue(h["render_readme"])


if __name__ == "__main__":
    unittest.main()
