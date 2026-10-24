"""Static HACS reviewer regression checks for the release archive."""
from pathlib import Path
import hashlib,json,ssl,unittest
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
 def test_pinned_ca(self):
  pem=(C/'orvibo_server_ca.pem').read_text()
  expected='f0046d72573a8e20cad178194385259f7338be2c9f9d12ac8646d1a24160ce2a'
  self.assertEqual(hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest(), expected)
 def test_diagnostics_redact_email(self):
  self.assertIn('_TO_REDACT = {CONF_PASSWORD_HASH, CONF_USER_ID, CONF_EMAIL}',(C/'diagnostics.py').read_text())
 def test_areas_preserved(self):
  self.assertIn('if newly_registered and device.uid in device_areas:',(C/'__init__.py').read_text())
  self.assertIn('previous_areas = configured_device_areas',(C/'config_flow.py').read_text())
 def test_english_labels(self):
  self.assertEqual(json.loads((C/'translations/en.json').read_text()),json.loads((C/'strings.json').read_text()))
 def test_capture_retries(self):
  s=(C/'capture.py').read_text();self.assertIn('if err.auth_rejected:',s);self.assertIn('if stop_auth_retry:',s);self.assertIn('_MAX_RECONNECT_DELAY_SECONDS',s)
if __name__=='__main__':unittest.main()
