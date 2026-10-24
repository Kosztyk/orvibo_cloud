"""Exercise the binary TLS connection and listener without an ORVIBO account."""

from contextlib import contextmanager
import hashlib
import importlib
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import MagicMock, patch


COMPONENT = Path(__file__).resolve().parents[1] / "custom_components/orvibo_cloud"
# Load protocol modules without executing Home Assistant integration setup.
PACKAGE = "_orvibo_security_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(COMPONENT)]
sys.modules[PACKAGE] = package
binary = importlib.import_module(f"{PACKAGE}.binary")
core = types.ModuleType("homeassistant.core")
core.HomeAssistant = object
constants = types.ModuleType(f"{PACKAGE}.const")
constants.ORVIBO_LOCK_EVENT = "orvibo_cloud_lock_event"
with patch.dict(sys.modules, {
    "homeassistant": types.ModuleType("homeassistant"),
    "homeassistant.core": core,
    f"{PACKAGE}.const": constants,
}):
    capture = importlib.import_module(f"{PACKAGE}.capture")


class TLSConnectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.root = Path(cls.directory.name)

        def openssl(*args):
            subprocess.run(
                ["openssl", *args], cwd=cls.root, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

        # Non-critical CA Basic Constraints reproduces ORVIBO's legacy encoding.
        for name in ("trusted", "untrusted"):
            openssl(
                "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                "-subj", f"/CN={name} test CA", "-keyout", f"{name}.key",
                "-out", f"{name}.pem", "-addext", "basicConstraints=CA:TRUE",
                "-addext", "keyUsage=critical,keyCertSign,cRLSign",
            )
            openssl(
                "req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=localhost",
                "-keyout", f"{name}-server.key", "-out", f"{name}-server.csr",
            )
            (cls.root / "server.ext").write_text(
                "subjectAltName=DNS:localhost\n"
                "basicConstraints=critical,CA:FALSE\n"
                "keyUsage=critical,digitalSignature,keyEncipherment\n"
                "extendedKeyUsage=serverAuth\n"
            )
            openssl(
                "x509", "-req", "-in", f"{name}-server.csr", "-days", "2",
                "-CA", f"{name}.pem", "-CAkey", f"{name}.key", "-CAcreateserial",
                "-extfile", "server.ext", "-out", f"{name}-server.pem",
            )
        cls.ca = cls.root / "trusted.pem"
        cls.fingerprint = hashlib.sha256(
            ssl.PEM_cert_to_DER_cert(cls.ca.read_text())
        ).hexdigest()

    @contextmanager
    def server(self, name):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(
            self.root / f"{name}-server.pem", self.root / f"{name}-server.key"
        )
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        listener.settimeout(5)
        errors = []

        def serve():
            try:
                raw, _ = listener.accept()
                with raw:
                    raw.settimeout(5)
                    with context.wrap_socket(raw, server_side=True) as secured:
                        secured.sendall(b"x")
                        secured.recv(1)
            except ssl.SSLError:
                pass  # Expected when the client rejects the certificate.
            except Exception as err:
                errors.append(err)

        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            yield listener.getsockname()
        finally:
            thread.join(6)
            listener.close()
            self.assertFalse(thread.is_alive(), "test TLS server did not stop")
            self.assertEqual(errors, [])

    def connect(self, host="localhost", server="trusted"):
        client = binary.OrviboBinaryClient(host, "test", "test", "test")
        with self.server(server) as address:
            raw = socket.create_connection(address, timeout=5)
            with (
                patch.object(binary, "_PINNED_SERVER_CA", self.ca),
                patch.object(binary, "_PINNED_SERVER_CA_SHA256", self.fingerprint),
                patch.object(binary, "_SERVER_CA_DIRECTORY", self.root / "absent"),
                patch.object(binary.socket, "create_connection", return_value=raw),
            ):
                try:
                    client._connect()
                    context = client._socket.context
                    self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                    self.assertTrue(context.check_hostname)
                    self.assertFalse(context.verify_flags & ssl.VERIFY_X509_STRICT)
                    self.assertEqual(client._socket.recv(1), b"x")
                    client._socket.sendall(b"y")
                finally:
                    client.close()
                    raw.close()

    def test_trusted_legacy_ca_and_matching_hostname_connect(self):
        self.connect()

    def test_wrong_hostname_is_rejected(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.connect(host="wrong.invalid")

    def test_untrusted_server_is_rejected(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.connect(server="untrusted")

    def test_changed_pinned_ca_fails_before_network_connection(self):
        client = binary.OrviboBinaryClient("localhost", "test", "test", "test")
        with (
            patch.object(binary, "_PINNED_SERVER_CA", self.ca),
            patch.object(binary.socket, "create_connection") as connection,
            self.assertRaisesRegex(binary.OrviboBinaryError, "fingerprint mismatch"),
        ):
            client._connect()
        connection.assert_not_called()


class CaptureRetryTests(unittest.TestCase):
    def listener(self):
        listener = capture.OrviboRawEventCapture(
            MagicMock(), "localhost", "test", "test", "test"
        )
        listener._stop_event = MagicMock()
        listener._stop_event.is_set.return_value = False
        return listener

    def test_rejected_login_stops_without_retry(self):
        listener = self.listener()
        rejection = binary.OrviboCaptureError(
            "login", binary.OrviboAuthenticationError("ORVIBO binary login was rejected")
        )
        with patch.object(capture, "OrviboBinaryClient") as factory:
            factory.return_value.capture_events.side_effect = rejection
            listener._run()
        factory.assert_called_once()
        listener._stop_event.wait.assert_not_called()
        factory.return_value.close.assert_called_once()

    def test_network_failure_uses_bounded_exponential_backoff(self):
        listener = self.listener()
        delays = []

        def wait(delay):
            delays.append(delay)
            if len(delays) == 9:
                listener._stop_event.is_set.return_value = True

        listener._stop_event.wait.side_effect = wait
        with (
            patch.object(capture, "OrviboBinaryClient") as factory,
            patch.object(capture.time, "monotonic", return_value=0),
        ):
            factory.return_value.capture_events.side_effect = binary.OrviboCaptureError(
                "connect", OSError("offline")
            )
            listener._run()
        self.assertEqual(delays, [5, 10, 20, 40, 80, 160, 300, 300, 300])
        self.assertEqual(factory.return_value.close.call_count, 9)

    def test_login_rejection_is_classified_for_capture(self):
        client = binary.OrviboBinaryClient("localhost", "test", "test", "test")
        with (
            patch.object(client, "_connect"),
            patch.object(client, "_handshake"),
            patch.object(client, "_send"),
            patch.object(client, "_receive_until_command", return_value=[{"cmd": 2, "status": 1}]),
            self.assertRaises(binary.OrviboCaptureError) as caught,
        ):
            client.capture_events(threading.Event(), MagicMock())
        self.assertTrue(caught.exception.auth_rejected)
        self.assertEqual(caught.exception.stage, "login")
