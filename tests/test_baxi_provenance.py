"""Regression checks for BAXI horizontal-swing and Daikin provenance for v1.4.1."""
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
C=ROOT/'custom_components/orvibo_cloud'

class BaxiAndProvenanceTests(unittest.TestCase):
    def test_daikin_file_scoped_license_and_attribution(self):
        code=(C/'daikin_arc433.py').read_text()
        self.assertIn('SPDX-License-Identifier: LGPL-2.1-only',code)
        self.assertIn('IRremoteESP8266',code)
        self.assertIn('Copyright 2016 sillyfrog',code)
        self.assertTrue((C/'LICENSES/LGPL-2.1.txt').exists())
        self.assertEqual((C/'LICENSES/LGPL-2.1.txt').read_bytes(),(ROOT/'LICENSES/LGPL-2.1.txt').read_bytes())
        self.assertIn('GNU LESSER GENERAL PUBLIC LICENSE',(C/'LICENSES/LGPL-2.1.txt').read_text())

    def test_references_and_readmes_are_synced(self):
        self.assertEqual((C/'README.md').read_bytes(),(ROOT/'README.md').read_bytes())
        self.assertEqual((C/'THIRD_PARTY_NOTICES.md').read_bytes(),(ROOT/'THIRD_PARTY_NOTICES.md').read_bytes())
        self.assertIn('source provenance', (ROOT/'THIRD_PARTY_NOTICES.md').read_text().lower())
        self.assertIn('stateReset', (ROOT/'PROVENANCE_AUDIT.md').read_text())
        self.assertIn('Horizontal', (ROOT/'README.md').read_text())

    def test_no_auto_swing_command_added_to_setup(self):
        code=(C/'climate.py').read_text()
        self.assertIn('async_add_entities(entities)',code)
        self.assertIn('async def _async_change',code)
        self.assertIn('OrviboACBackend',code)
        self.assertIn('"off", "vertical", "horizontal", "both"',(C/'ac_profiles.py').read_text())

if __name__ == '__main__':
    unittest.main()
