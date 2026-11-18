"""Static HACS reviewer regression checks for the release archive."""
from pathlib import Path
import json,unittest
R=Path(__file__).resolve().parents[1]
C=R/'custom_components/orvibo_cloud'
class HACSReviewTests(unittest.TestCase):
 def test_hostname_and_certificate(self):
  s=(C/'binary.py').read_text()
  self.assertIn('context.check_hostname = True',s)
  self.assertIn('context.verify_mode = ssl.CERT_REQUIRED',s)
  self.assertIn('context.load_verify_locations',s)
  self.assertIn('VERIFY_X509_STRICT',s)
  self.assertNotIn('ssl.CERT_NONE',s)
 def test_no_bundled_vendor_client_credentials(self):
  for name in ('orvibo_client_cert.pem','orvibo_client_key.pem'):
   self.assertFalse(list(C.rglob(name)), f'Withdrawn client credential found: {name}')
 def test_areas_preserved(self):
  self.assertIn('if newly_registered and device.uid in device_areas:',(C/'__init__.py').read_text())
  self.assertIn('previous_areas = configured_device_areas',(C/'config_flow.py').read_text())
 def test_english_labels(self):
  self.assertEqual(json.loads((C/'translations/en.json').read_text()),json.loads((C/'strings.json').read_text()))
 def test_capture_retries(self):
  s=(C/'capture.py').read_text();self.assertIn('if err.auth_rejected:',s);self.assertIn('if stop_retry:',s);self.assertIn('_MAX_RECONNECT_DELAY_SECONDS',s)
if __name__=='__main__':unittest.main()
