"""Verify the production release layout and preserve existing device support."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
C = ROOT / 'custom_components/orvibo_cloud'
VERSION = '1.4.2'


class ProductionReleaseTests(unittest.TestCase):
    def test_release_manifest_docs_and_identical_readme(self):
        manifest = json.loads((C / 'manifest.json').read_text())
        self.assertEqual(manifest['domain'], 'orvibo_cloud')
        self.assertEqual(manifest['version'], VERSION)
        self.assertEqual((C / 'README.md').read_bytes(), (ROOT / 'README.md').read_bytes())
        self.assertEqual((C / 'THIRD_PARTY_NOTICES.md').read_bytes(), (ROOT / 'THIRD_PARTY_NOTICES.md').read_bytes())
        for path in ('RELEASE_NOTES_1.4.1.md', f'RELEASE_NOTES_{VERSION}.md',
                     'VALIDATION.md', 'HACS_PUBLISHING.md',
                     'LS175_GUIDE.md', 'BAXI_VALIDATION_GUIDE.md',
                     'PROVENANCE_AUDIT.md', 'LICENSES/LGPL-2.1.txt'):
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())
        self.assertFalse((ROOT / 'LS175_BETA_GUIDE.md').exists())
        self.assertFalse((ROOT / 'BAXI_BETA_141B9_GUIDE.md').exists())

    def test_exact_vivax_profile_and_kaysun_swing_kept(self):
        source = (C / 'ac_profiles.py').read_text()
        midea = (C / 'midea_48.py').read_text()
        self.assertIn('("5", "2", "7579")', source)
        self.assertIn('MIDEA_SWING_V_TOGGLE = 0xA202FFFFFF7E', midea)
        self.assertNotIn('MIDEA_SWING_V_TOGGLE = 0xA201FFFFFF7C', midea)
        self.assertFalse((C / 'vivax_scenes.py').exists())
        self.assertFalse((C / 'vivax_climate.py').exists())

    def test_baxi_and_ls175_production_features(self):
        self.assertIn('("off", "vertical", "horizontal", "both")', (C / 'ac_profiles.py').read_text())
        self.assertIn('0x00FFA25D', (C / 'blaupunkt_ls175.py').read_text())
        self.assertIn('Platform.SWITCH', (C / 'const.py').read_text())
        self.assertIn('async_step_devices', (C / 'config_flow.py').read_text())
        self.assertIn('async_step_area', (C / 'config_flow.py').read_text())

    def test_release_workflows_and_publishing_safety(self):
        publisher = (ROOT / 'scripts/publish_v1.4.1.sh').read_text()
        workflow = (ROOT / '.github/workflows/release.yml').read_text()
        validate = (ROOT / '.github/workflows/validate.yml').read_text()
        self.assertIn("VERSION='1.4.1'", publisher)
        self.assertIn('EXPECTED_BASE=', publisher)
        self.assertIn('--check', publisher)
        self.assertIn('--publish', publisher)
        self.assertIn('gh run watch', publisher)
        self.assertIn('gh release upload', publisher)
        self.assertIn('refs/tags/$TAG', publisher)
        self.assertIn('gh release create', workflow)
        self.assertIn('RELEASE_NOTES_${VERSION}.md', workflow)
        self.assertIn('hacs/action@main', validate)
        self.assertIn('home-assistant/actions/hassfest@master', validate)
        for text in (workflow, validate):
            self.assertIn('python -m pip install -r requirements-test.txt', text)
        deps = (ROOT / 'requirements-test.txt').read_text()
        self.assertIn('pycryptodome', deps)
        self.assertIn('aiohttp', deps)
        self.assertIn('cryptography', deps)

    def test_stable_builder_packages_the_integration_and_source(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as out:
            process = subprocess.run(
                [sys.executable, str(ROOT / 'tools/build_release_archives.py'),
                 '--output', out, '--version', VERSION],
                text=True, capture_output=True,
            )
            self.assertEqual(process.returncode, 0, msg=process.stdout + process.stderr)
            install = Path(out) / f'orvibo_cloud_v{VERSION}_ha_install.zip'
            full = Path(out) / f'orvibo_cloud_v{VERSION}_full_source.zip'
            self.assertTrue(install.is_file())
            self.assertTrue(full.is_file())
            with ZipFile(install) as z:
                self.assertIsNone(z.testzip())
                members = z.namelist()
                self.assertIn('custom_components/orvibo_cloud/manifest.json', members)
                self.assertIn('custom_components/orvibo_cloud/LICENSES/LGPL-2.1.txt', members)
                manifest = json.loads(z.read('custom_components/orvibo_cloud/manifest.json'))
                self.assertEqual(manifest['version'], VERSION)
                self.assertNotIn('tools/check_repository.py', members)
                self.assertTrue(all(x.startswith('custom_components/orvibo_cloud/') for x in members))
            with ZipFile(full) as z:
                self.assertIsNone(z.testzip())
                self.assertIn(f'orvibo_cloud_v{VERSION}/LICENSES/LGPL-2.1.txt', z.namelist())
                self.assertIn(f'orvibo_cloud_v{VERSION}/RELEASE_NOTES_{VERSION}.md', z.namelist())
                self.assertIn(f'orvibo_cloud_v{VERSION}/BAXI_VALIDATION_GUIDE.md', z.namelist())
                self.assertFalse(any('/__pycache__/' in x for x in z.namelist()))

    def test_stable_builder_rejects_prerelease_and_mismatched_versions(self):
        file = ROOT / 'tools/build_release_archives.py'
        spec = importlib.util.spec_from_file_location('orvibo_stable_release', file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as out:
            with self.assertRaisesRegex(ValueError, 'Only stable numeric versions'):
                module.build(ROOT, Path(out), '1.4.2b5')
            with self.assertRaisesRegex(ValueError, 'Manifest version mismatch'):
                module.build(ROOT, Path(out), '1.4.1')


if __name__ == '__main__':
    unittest.main()
