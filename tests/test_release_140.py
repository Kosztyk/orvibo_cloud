"""Stable release invariants: no beta scene fallback, tagged workflows, and docs."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / 'custom_components/orvibo_cloud'


class StableReleaseTests(unittest.TestCase):
    def test_stable_manifest_and_release_note(self):
        manifest = json.loads((C/'manifest.json').read_text())
        self.assertEqual(manifest['version'], '1.4.0')
        self.assertEqual(manifest['domain'], 'orvibo_cloud')
        self.assertTrue((ROOT/'RELEASE_NOTES_1.4.0.md').exists())
        self.assertNotIn('manual beta', (ROOT/'README.md').read_text().lower())

    def test_exact_vivax_profile_and_kaysun_swing(self):
        source = (C/'ac_profiles.py').read_text()
        midea = (C/'midea_48.py').read_text()
        self.assertIn('("5", "2", "7579")', source)
        self.assertIn('MIDEA_SWING_V_TOGGLE = 0xA202FFFFFF7E', midea)
        self.assertNotIn('MIDEA_SWING_V_TOGGLE = 0xA201FFFFFF7C', midea)
        self.assertNotIn('vivax_scenes', source)
        self.assertNotIn('vivax_scenes', (C/'climate.py').read_text())
        self.assertFalse((C/'vivax_scenes.py').exists())
        self.assertFalse((C/'vivax_climate.py').exists())

    def test_publishing_gate_and_code_provenance(self):
        release_workflow = (ROOT/'.github/workflows/release.yml').read_text()
        script = (ROOT/'scripts/publish_v1.4.0.sh').read_text()
        self.assertIn('tags:', release_workflow)
        self.assertIn('RELEASE_NOTES_${VERSION}.md', release_workflow)
        self.assertIn('gh release create', release_workflow)
        self.assertIn('EXPECTED_BASE=', script)
        self.assertIn('gh run watch', script)
        self.assertIn('git -C "$CHECKOUT" push origin', script)
        self.assertIn('pull/5', (ROOT/'THIRD_PARTY_NOTICES.md').read_text())
        self.assertEqual((C/'README.md').read_bytes(), (ROOT/'README.md').read_bytes())

    def test_release_and_ci_install_all_test_dependencies(self):
        """The standalone BAXI diagnostic imports aiohttp at test-import time."""
        deps = (ROOT / 'requirements-test.txt').read_text()
        self.assertIn('aiohttp', deps)
        self.assertIn('pycryptodome', deps)
        script = (ROOT / 'scripts/publish_v1.4.0.sh').read_text()
        self.assertIn('"$CHECKOUT/requirements-test.txt"', script)
        for workflow in ('validate.yml', 'release.yml'):
            contents = (ROOT / '.github/workflows' / workflow).read_text()
            with self.subTest(workflow=workflow):
                self.assertIn('python -m pip install -r requirements-test.txt', contents)

    def test_beta_traces_not_shipped(self):
        self.assertEqual(list(ROOT.glob('RELEASE_NOTES_1.4.0b*.md')), [])
        self.assertEqual(list(C.glob('RELEASE_NOTES_1.4.0b*.md')), [])
        self.assertFalse((C/'BETA_TESTING.md').exists())


if __name__ == '__main__':
    unittest.main()
