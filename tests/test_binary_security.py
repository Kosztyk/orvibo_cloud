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

from cryptography import x509
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


COMPONENT = Path(__file__).resolve().parents[1] / "custom_components/orvibo_cloud"
# Load protocol modules without executing Home Assistant integration setup.
PACKAGE = "_orvibo_security_tests"
package = types.ModuleType(PACKAGE)
package.__path__ = [str(COMPONENT)]
sys.modules[PACKAGE] = package
binary = importlib.import_module(f"{PACKAGE}.binary")
core = types.ModuleType("homeassistant.core")
core.HomeAssistant = object
core.callback = lambda func: func
dispatcher = types.ModuleType("homeassistant.helpers.dispatcher")
dispatcher.async_dispatcher_send = MagicMock()
constants = types.ModuleType(f"{PACKAGE}.const")
constants.ORVIBO_LOCK_EVENT = "orvibo_cloud_lock_event"
with patch.dict(sys.modules, {
    "homeassistant": types.ModuleType("homeassistant"),
    "homeassistant.core": core,
    "homeassistant.helpers.dispatcher": dispatcher,
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

        # Generate the legacy CA through a config file rather than `-addext`.
        # This works with macOS LibreSSL as well as OpenSSL 3. The Basic
        # Constraints extension remains non-critical, matching ORVIBO's CA.
        ca_config = cls.root / "ca.cnf"
        ca_config.write_text(
            "[req]\n"
            "distinguished_name = dn\n"
            "x509_extensions = ca_ext\n"
            "[dn]\n"
            "[ca_ext]\n"
            "basicConstraints = CA:TRUE\n"
            "keyUsage = critical,keyCertSign,cRLSign\n"
        )
        for name in ("trusted", "untrusted"):
            openssl(
                "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2",
                "-subj", f"/CN={name} test CA", "-keyout", f"{name}.key",
                "-out", f"{name}.pem", "-config", str(ca_config),
                "-extensions", "ca_ext",
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
        openssl(
            "req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=ORVIBO test client",
            "-keyout", "client.key", "-out", "client.csr",
        )
        (cls.root / "client.ext").write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "keyUsage=critical,digitalSignature,keyEncipherment\n"
            "extendedKeyUsage=clientAuth\n"
        )
        openssl(
            "x509", "-req", "-in", "client.csr", "-days", "2",
            "-CA", "trusted.pem", "-CAkey", "trusted.key", "-CAcreateserial",
            "-extfile", "client.ext", "-out", "client.pem",
        )
        cls.ca = cls.root / "trusted.pem"
        cls.fingerprint = hashlib.sha256(
            ssl.PEM_cert_to_DER_cert(cls.ca.read_text())
        ).hexdigest()
        leaf = x509.load_pem_x509_certificate((cls.root / "trusted-server.pem").read_bytes())
        cls.pin = hashlib.sha256(
            leaf.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        ).hexdigest()

    def setUp(self):
        for name, path in (
            ("_CERT_PATH", self.root / "client.pem"),
            ("_KEY_PATH", self.root / "client.key"),
        ):
            patcher = patch.object(binary, name, path)
            patcher.start()
            self.addCleanup(patcher.stop)

    @contextmanager
    def server(self, name, *, expect_rejection=False):
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        if name == "bundled":
            context.load_cert_chain(
                self.root / "trusted-server.pem", self.root / "trusted-server.key"
            )
        else:
            context.load_cert_chain(
                self.root / f"{name}-server.pem", self.root / f"{name}-server.key"
            )
        if name == "trusted":
            context.load_verify_locations(cafile=str(self.ca))
            context.verify_mode = ssl.CERT_REQUIRED
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
                        if secured.recv(1) and expect_rejection:
                            errors.append("the rejected peer received application data")
            except (ssl.SSLError, ConnectionResetError, BrokenPipeError) as err:
                # Some OSes reset a connection when client rejects the certificate.
                if not expect_rejection:
                    errors.append(err)
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

    def connect(self, host="localhost", server="trusted", *, pin=None):
        client = binary.OrviboBinaryClient(host, "test", "test", "test")
        expected_cas = set(ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT).get_ca_certs(binary_form=True))
        expected_cas.add(ssl.PEM_cert_to_DER_cert(self.ca.read_text()))
        with self.server(
            server, expect_rejection=(
                host != "localhost" or server != "trusted" or pin not in (None, self.pin)
            )
        ) as address:
            with (
                tempfile.TemporaryDirectory(dir=self.root) as trust_directory,
                socket.create_connection(address, timeout=5) as raw,
                patch.object(binary, "_PINNED_SERVER_CA", self.ca),
                patch.object(binary, "_PINNED_SERVER_CA_SHA256", self.fingerprint),
                patch.object(binary, "_SERVER_CA_DIRECTORY", Path(trust_directory)),
                patch.object(binary, "ORVIBO_HOSTS", ("localhost", "wrong.invalid")),
                patch.object(binary.socket, "create_connection", return_value=raw),
            ):
                if pin is not None:
                    (Path(trust_directory) / f"{host}.spki").write_text(pin, encoding="ascii")
                try:
                    client._connect()
                    context = client._socket.context
                    self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
                    self.assertTrue(context.check_hostname)
                    self.assertFalse(context.verify_flags & ssl.VERIFY_X509_STRICT)
                    self.assertEqual(set(context.get_ca_certs(binary_form=True)), expected_cas)
                    self.assertEqual(client._socket.recv(1), b"x")
                    client._socket.sendall(b"y")
                finally:
                    client.close()

    def test_trusted_legacy_ca_connects_without_a_pin_file(self):
        self.connect()

    def test_trusted_legacy_ca_with_matching_optional_pin_connects(self):
        self.connect(pin=self.pin)

    def test_wrong_hostname_is_rejected(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.connect(host="wrong.invalid")

    def test_untrusted_server_is_rejected(self):
        with self.assertRaises(ssl.SSLCertVerificationError):
            self.connect(server="untrusted")

    def test_changed_pinned_ca_fails_before_network_connection(self):
        client = binary.OrviboBinaryClient("homemate.orvibo.com", "test", "test", "test")
        with (
            patch.object(binary, "_PINNED_SERVER_CA", self.ca),
            patch.object(binary, "_SERVER_CA_DIRECTORY", self.root / "absent"),
            patch.object(binary.socket, "create_connection") as connection,
            self.assertRaisesRegex(binary.OrviboServerIdentityError, "fingerprint mismatch"),
        ):
            client._connect()
        connection.assert_not_called()


    def test_wrong_pin_with_valid_ca_and_hostname_is_rejected(self):
        with self.assertRaisesRegex(binary.OrviboServerIdentityError, "was not approved"):
            self.connect(pin="1" * 64)

    def test_bundled_certificate_is_rejected_without_any_pin_before_commands_or_push_login(self):
        for operation in ("command", "push"):
            with self.subTest(operation=operation), self.server(
                "bundled", expect_rejection=True
            ) as address:
                client = binary.OrviboBinaryClient("localhost", "test", "test", "test")
                with (
                    socket.create_connection(address, timeout=5) as raw,
                    patch.object(binary, "ORVIBO_HOSTS", ("localhost",)),
                    patch.object(binary, "_PINNED_SERVER_CA", self.ca),
                    patch.object(binary, "_PINNED_SERVER_CA_SHA256", self.fingerprint),
                    patch.object(binary, "_SHARED_CLIENT_SPKI_SHA256", self.pin),
                    patch.object(binary, "_SERVER_CA_DIRECTORY", self.root / "absent"),
                    patch.object(binary.socket, "create_connection", return_value=raw),
                    patch.object(client, "_handshake") as handshake,
                    patch.object(client, "_login") as login,
                ):
                    if operation == "command":
                        with self.assertRaisesRegex(binary.OrviboServerIdentityError, "shared client key"):
                            client.control_device("test-device", "test-hub", "open", 100)
                    else:
                        with self.assertRaises(binary.OrviboCaptureError) as caught:
                            client.capture_events(threading.Event(), MagicMock())
                        self.assertTrue(caught.exception.identity_rejected)
                    handshake.assert_not_called()
                    login.assert_not_called()
                    self.assertIsNone(client._socket)


class PinConfigurationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.directory = Path(directory.name)
        self.host = "homemate.orvibo.com"
        self.file = self.directory / f"{self.host}.spki"
        patcher = patch.object(binary, "_SERVER_CA_DIRECTORY", self.directory)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_invalid_optional_pin_refuses_to_open_a_socket(self):
        self.file.write_text("not-a-digest")
        client = binary.OrviboBinaryClient(self.host, "test", "test", "test")
        with (
            patch.object(binary.socket, "create_connection") as connection,
            self.assertRaisesRegex(binary.OrviboServerIdentityError, "invalid digest"),
        ):
            client._connect()
        connection.assert_not_called()

    def test_pins_are_host_specific_and_support_rotation(self):
        self.file.write_text("A" * 64 + "\n" + "b" * 64 + "\n")
        self.assertEqual(binary.load_binary_server_pins(self.host), {"a" * 64, "b" * 64})
        self.assertEqual(binary.load_binary_server_pins("usa.orvibo.com"), set())

    def test_missing_client_credentials_fail_before_opening_a_socket(self):
        self.assertFalse((COMPONENT / "orvibo_client_cert.pem").exists())
        self.assertFalse((COMPONENT / "orvibo_client_key.pem").exists())
        client = binary.OrviboBinaryClient(self.host, "test", "test", "test")
        with (
            patch.object(binary.socket, "create_connection") as connection,
            self.assertRaisesRegex(binary.OrviboBinaryError, "certificate files are missing"),
        ):
            client._connect()
        connection.assert_not_called()

    def test_invalid_or_shared_key_pin_is_rejected(self):
        for value in ("not-a-digest", binary._SHARED_CLIENT_SPKI_SHA256):
            with self.subTest(value=value):
                self.file.write_text(value)
                with self.assertRaises(binary.OrviboServerIdentityError):
                    binary.load_binary_server_pins(self.host)


class ControlReplyTests(unittest.TestCase):
    def send(self, batches):
        client = binary.OrviboBinaryClient("localhost", "test", "test", "test")
        request = {"cmd": 15, "deviceId": "target", "uid": "hub", "serial": 41, "uniSerial": 500}
        with (
            patch.object(client, "_connect"),
            patch.object(client, "_handshake"),
            patch.object(client, "_login"),
            patch.object(client, "_send"),
            patch.object(client, "_control_payload", return_value=request),
            patch.object(client, "_receive", side_effect=batches),
        ):
            return client.control_device("target", "hub", "open", 100)

    def test_push_from_same_device_does_not_hide_later_rejection(self):
        unrelated = {"cmd": 42, "deviceId": "target", "serial": 40, "value1": 100}
        with self.assertRaisesRegex(binary.OrviboBinaryError, "status=1"):
            self.send(([unrelated], [{"cmd": 15, "status": 1}]))

    def test_even_correlated_telemetry_does_not_acknowledge_a_command(self):
        telemetry = {"cmd": 42, "deviceId": "target", "serial": 41, "status": 0, "value1": 100}
        with self.assertRaisesRegex(binary.OrviboBinaryError, "status=1"):
            self.send(([telemetry], [{"cmd": 15, "serial": 41, "status": 1}]))
        with self.assertRaisesRegex(binary.OrviboBinaryError, "matching acknowledgement"):
            self.send(([telemetry], []))

    def test_wrong_acknowledgements_do_not_end_the_read(self):
        bad_acknowledgements = [
            {"cmd": 15, "deviceId": "other", "status": 0},
            {"cmd": 15, "uid": "other-hub", "status": 0},
            {"cmd": 15, "serial": 41, "uniSerial": 499, "status": 0},
            {"cmd": 15, "serial": 41, "value1": 100},
        ]
        with self.assertRaisesRegex(binary.OrviboBinaryError, "status=2"):
            self.send((bad_acknowledgements, [{"cmd": 15, "status": 2}]))

    def test_legacy_acknowledgement_ignores_uncorrelated_feedback(self):
        packets = [
            {"cmd": 42, "deviceId": "target", "value1": 99},
            {"cmd": 15, "status": 0, "value1": 100},
        ]
        self.assertEqual(self.send((packets,)), (None, None, None, None))

    def test_correlated_feedback_is_returned_after_acknowledgement(self):
        telemetry = {"cmd": 42, "deviceId": "target", "serial": "41", "value1": 55}
        acknowledgement = {"cmd": "15", "uniSerial": "500", "status": "0"}
        self.assertEqual(self.send(([telemetry], [acknowledgement])), (55, None, None, None))

    def test_malformed_status_does_not_update_assumed_state(self):
        for status in (None, False, "private-value"):
            with self.subTest(status=status), self.assertRaisesRegex(
                binary.OrviboBinaryError, "status=non_numeric"
            ):
                self.send(([{"cmd": 15, "status": status}],))


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

    def test_server_identity_failure_stops_without_retry(self):
        listener = self.listener()
        listener._stop_event.is_set.side_effect = [False, False, True]
        error = binary.OrviboCaptureError(
            "connect", binary.OrviboServerIdentityError("unapproved peer")
        )
        with patch.object(capture, "OrviboBinaryClient") as factory:
            factory.return_value.capture_events.side_effect = error
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
        connected = MagicMock()
        with (
            patch.object(client, "_connect"),
            patch.object(client, "_handshake"),
            patch.object(client, "_send"),
            patch.object(client, "_receive_until_command", return_value=[{"cmd": 2, "status": 1}]),
            self.assertRaises(binary.OrviboCaptureError) as caught,
        ):
            client.capture_events(threading.Event(), MagicMock(), on_connected=connected)
        self.assertTrue(caught.exception.auth_rejected)
        self.assertEqual(caught.exception.stage, "login")
        connected.assert_not_called()

    def test_stream_connected_callback_runs_after_login(self):
        client = binary.OrviboBinaryClient("localhost", "test", "test", "test")
        stop = threading.Event()
        stages = []

        def connected():
            stages.append("connected")
            stop.set()

        with (
            patch.object(client, "_connect", side_effect=lambda: stages.append("connect")),
            patch.object(client, "_handshake", side_effect=lambda: stages.append("handshake")),
            patch.object(client, "_login", side_effect=lambda: stages.append("login")),
        ):
            client.capture_events(stop, MagicMock(), on_connected=connected)
        self.assertEqual(stages, ["connect", "handshake", "login", "connected"])

    def test_reconnect_only_requests_resync_after_previous_authenticated_stream(self):
        hass = MagicMock()
        hass.loop.call_soon_threadsafe.side_effect = lambda target, *args: target(*args)
        resync = MagicMock()
        listener = capture.OrviboRawEventCapture(
            hass, "localhost", "test", "test", "test", on_reconnect=resync
        )

        def connect_then_disconnect(stop_event, packet_callback, *, on_connected):
            on_connected()
            raise binary.OrviboCaptureError("stream", OSError("connection closed"))

        waits = 0

        def stop_after_reconnect(delay):
            nonlocal waits
            waits += 1
            if waits == 2:
                listener._stop_event.set()

        with (
            patch.object(capture, "OrviboBinaryClient") as factory,
            patch.object(listener._stop_event, "wait", side_effect=stop_after_reconnect),
            patch.object(capture.time, "monotonic_ns", return_value=123),
        ):
            factory.return_value.capture_events.side_effect = connect_then_disconnect
            listener._run()

        self.assertEqual(factory.return_value.capture_events.call_count, 2)
        resync.assert_called_once_with(123)

    def test_same_door_push_can_refresh_entity_even_when_bus_event_is_deduplicated(self):
        hass = MagicMock()
        hass.loop.call_soon_threadsafe.side_effect = lambda target, *args: target(*args)
        listener = capture.OrviboRawEventCapture(
            hass, "localhost", "test", "test", "test", door_status_signal="test-door-signal"
        )
        packet = {"cmd": 42, "uid": "door", "properties": {"door_status": "open"}}
        with (
            patch.object(capture, "async_dispatcher_send") as send,
            patch.object(capture.time, "monotonic_ns", side_effect=(110, 200)),
        ):
            listener._capture(packet)
            listener._capture(packet)
        self.assertEqual([call.args[-1] for call in send.call_args_list], [110, 200])
        self.assertTrue(all(call.args[1] == "test-door-signal" for call in send.call_args_list))
        hass.bus.async_fire.assert_called_once()
