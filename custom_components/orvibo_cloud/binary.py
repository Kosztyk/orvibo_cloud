"""ORVIBO mutual-TLS binary cloud client used for device discovery."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import json
import hashlib
import logging
from pathlib import Path
import secrets
import select
import socket
import ssl
import struct
import time
from threading import Event
from typing import Any, Final
import zlib

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

from .control import OrviboInfrared, is_tv_button_order
from .protocol import OrviboDevice, extract_devices

_LOGGER = logging.getLogger(__name__)

_STATIC_KEY: Final = b"khggd54865SNJHGF"
_CLIENT_VERSION: Final = "5.2.6.302"
_PORT: Final = 10002
_HEADER_SIZE: Final = 42
_MAX_DEVICE_PAGES: Final = 20
_SESSION_RESPONSE_IDLE_TIMEOUT: Final = 0.2
_CERT_PATH: Final = Path(__file__).with_name("orvibo_client_cert.pem")
_KEY_PATH: Final = Path(__file__).with_name("orvibo_client_key.pem")
# Legacy ORVIBO 10002 self-signed CA corroborated in two established public
# ORVIBO integrations and the user's TLS diagnostic; not a WebPKI root.
_PINNED_SERVER_CA: Final = Path(__file__).with_name("orvibo_server_ca.pem")
_PINNED_SERVER_CA_SHA256: Final = "f0046d72573a8e20cad178194385259f7338be2c9f9d12ac8646d1a24160ce2a"

# Persistent, operator-provided regional CA trust anchors. Never auto-import
# a certificate from the network: its authenticity must be checked out-of-band.
# Store the PEM outside custom_components so updates do not delete it.
_SERVER_CA_DIRECTORY: Final = Path(__file__).resolve().parents[2] / "orvibo_trust"


def _safe_protocol_number(value: object) -> int | None:
    """Keep protocol diagnostics numeric; never echo remote text or IDs."""

    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if -(2**63) <= value < 2**63 else None
    if isinstance(value, str) and len(value) <= 20:
        try:
            number = int(value)
        except ValueError:
            return None
        return number if -(2**63) <= number < 2**63 else None
    return None


def _matches_control_reply(
    packet: Mapping[str, Any], request: Mapping[str, Any]
) -> bool:
    """Match a command acknowledgement or a state update for this target."""

    command = _safe_protocol_number(packet.get("cmd"))
    if command not in (15, 42):
        return False
    for key in ("deviceId", "uid"):
        value = packet.get(key)
        if value not in (None, "") and str(value) != str(request.get(key)):
            return False

    # A broadcast for this exact device may use its own sequence number.
    # The hardware UID alone is insufficient: Allone children share a hub.
    if command == 42 and packet.get("deviceId") not in (None, ""):
        return any(
            key in packet
            for key in ("status", "value1", "value2", "value3", "value4", "properties")
        )

    sequence_matches: bool | None = None
    for key in ("serial", "uniSerial"):
        if key in packet:
            sequence_matches = (
                _safe_protocol_number(packet[key]) is not None
                and _safe_protocol_number(packet[key])
                == _safe_protocol_number(request.get(key))
            )
            if not sequence_matches:
                return False

    if command == 42:
        return sequence_matches is True and any(
            key in packet
            for key in ("status", "value1", "value2", "value3", "value4", "properties")
        )
    # This client opens a separate connection for each command. A legacy
    # cmd=15 acknowledgement may omit both identifiers and sequence numbers.
    return "status" in packet


def _control_reply_summary(
    packet: Mapping[str, Any], request: Mapping[str, Any]
) -> dict[str, Any]:
    """Describe routing/correlation without exposing packet payloads."""

    status = _safe_protocol_number(packet.get("status"))
    summary: dict[str, Any] = {
        "cmd": _safe_protocol_number(packet.get("cmd")),
        "status": status if status is not None else (
            "non_numeric" if "status" in packet else None
        ),
        "matching": _matches_control_reply(packet, request),
        "has_state": any(
            key in packet for key in ("value1", "value2", "value3", "value4", "properties")
        ),
    }
    for key, label in (
        ("deviceId", "device"), ("uid", "uid"),
        ("serial", "serial"), ("uniSerial", "uni_serial"),
    ):
        if key in packet:
            summary[f"{label}_matches"] = str(packet[key]) == str(request.get(key))
    return summary


class OrviboBinaryError(Exception):
    """Raised when an ORVIBO binary operation fails."""


class OrviboAuthenticationError(OrviboBinaryError):
    """A confirmed rejection of the binary ORVIBO cloud login."""


class OrviboCaptureError(OrviboBinaryError):
    """Describe a capture failure without exposing connection credentials."""

    def __init__(self, stage: str, cause: BaseException) -> None:
        self.stage = stage
        self.auth_rejected = isinstance(cause, OrviboAuthenticationError)
        self.error_type = type(cause).__name__
        if isinstance(cause, OSError):
            self.detail = f"{self.error_type} (errno={cause.errno!r})"
        elif isinstance(cause, OrviboBinaryError):
            self.detail = _safe_binary_error_detail(cause)
        else:
            self.detail = self.error_type
        super().__init__(f"stage={stage}, detail={self.detail}")


def _safe_binary_error_detail(error: OrviboBinaryError) -> str:
    """Return bounded diagnostics from locally generated protocol errors."""

    message = str(error)
    if message.startswith("ORVIBO binary handshake did not return a key"):
        return "handshake response did not contain a key"
    if message == "ORVIBO binary handshake returned an invalid key":
        return "handshake response contained an invalid key"
    if message.startswith("ORVIBO binary login did not return a response"):
        return "login response was not received"
    if message.startswith("ORVIBO binary login was rejected"):
        return "login was rejected"
    if message == "ORVIBO capture socket is not connected":
        return "capture socket is not connected"
    if message == "ORVIBO capture connection was closed":
        return "capture connection was closed"
    if message == "ORVIBO client certificate files are missing":
        return "client certificate files are missing"
    return "binary protocol operation failed"


class OrviboBinaryClient:
    """Blocking binary protocol client. Run it in HA's executor."""

    def __init__(
        self,
        host: str,
        email: str,
        password_md5: str,
        family_id: str,
    ) -> None:
        self._host = host
        self._email = email
        self._password_md5 = password_md5
        self._family_id = family_id
        self._socket: ssl.SSLSocket | None = None
        self._receive_buffer = bytearray()
        self._dynamic_key: bytes | None = None
        self._session_id = "0" * 32
        self._serial = int(time.time())
        self._identifier = secrets.token_hex(8)
        self._stop_commands: frozenset[int] = frozenset()

    def discover(self) -> tuple[OrviboDevice, ...]:
        """Connect, authenticate, query, and normalize all returned devices."""

        packets: list[dict[str, Any]] = []
        try:
            self._connect()
            packets.extend(self._handshake())
            packets.extend(self._login())
            packets.extend(self._query_devices())
        finally:
            self.close()

        shapes = [
            {"cmd": packet.get("cmd"), "keys": sorted(packet.keys())}
            for packet in packets
        ]
        devices = extract_devices(packets)
        _LOGGER.debug(
            "ORVIBO binary discovery returned %d packets, %d devices, shapes=%s",
            len(packets),
            len(devices),
            shapes,
        )
        return devices

    def control_device(
        self,
        device_id: str,
        device_uid: str,
        order: str,
        value1: int,
        value2: int = 0,
        value3: int = 0,
        value4: int = 0,
        properties: Mapping[str, Any] | None = None,
        infrared: OrviboInfrared | None = None,
    ) -> tuple[int | None, int | None, int | None, int | None]:
        """Open a binary session and send one device control command."""

        if not device_id or not device_uid:
            raise OrviboBinaryError("ORVIBO control identifiers are missing")
        try:
            self._connect()
            self._handshake()
            self._login()
            # Generate the request after login so its serial follows the
            # handshake/login serials on this connection.
            request = self._control_payload(
                device_id, device_uid, order, value1, value2, value3, value4, properties, infrared
            )
            self._send(request)
            packets: list[dict[str, Any]] = []
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                batch = self._receive(
                    timeout=max(0.0, deadline - time.monotonic()),
                    idle_timeout=_SESSION_RESPONSE_IDLE_TIMEOUT,
                )
                packets.extend(batch)
                if not batch or any(
                    _matches_control_reply(packet, request) for packet in batch
                ):
                    break
        finally:
            self.close()

        replies = [packet for packet in packets if _matches_control_reply(packet, request)]
        rejected = next(
            (packet for packet in replies if packet.get("status") not in (None, 0, "0")),
            None,
        )
        if rejected is not None or not replies:
            summary = [_control_reply_summary(packet, request) for packet in packets[:30]]
            safe_order = order if is_tv_button_order(order) or order in {
                "open", "close", "stop", "on", "off", "set property",
                "fast move to level", "fast color temperature", "rf control", "ir control",
            } else "withheld"
            _LOGGER.warning(
                "ORVIBO control reply diagnostics: order=%s packets=%s",
                safe_order,
                json.dumps(summary, ensure_ascii=True, separators=(",", ":")),
            )
        if not replies:
            raise OrviboBinaryError(
                "ORVIBO control did not return a matching response; "
                "see control reply diagnostics in the log"
            )
        if rejected is not None:
            status = _safe_protocol_number(rejected.get("status"))
            command = _safe_protocol_number(rejected.get("cmd"))
            raise OrviboBinaryError(
                "ORVIBO control was rejected "
                f"(status={status if status is not None else 'non_numeric'}, "
                f"response_cmd={command})"
            )
        # A cmd=15 acknowledgement can echo requested values; these are not
        # measured device state. Only a matching cmd=42 can supply state.
        response = next(
            (packet for packet in replies if _safe_protocol_number(packet.get("cmd")) == 42),
            {},
        )
        values: list[int | None] = []
        for key in ("value1", "value2", "value3", "value4"):
            try:
                values.append(int(response[key]))
            except (KeyError, TypeError, ValueError):
                values.append(None)
        return values[0], values[1], values[2], values[3]

    def capture_events(
        self,
        stop_event: Event,
        callback: Callable[[Mapping[str, Any]], None],
    ) -> None:
        """Keep one authenticated session open and deliver unsolicited packets."""

        stage = "connect"
        try:
            self._connect()
            stage = "handshake"
            self._handshake()
            stage = "login"
            self._login()
            stage = "stream"
            while not stop_event.is_set():
                if self._socket is None:
                    raise OrviboBinaryError("ORVIBO capture socket is not connected")
                readable, _, _ = select.select([self._socket], [], [], 1.0)
                if not readable:
                    continue
                data = self._socket.recv(65536)
                if not data:
                    raise OrviboBinaryError("ORVIBO capture connection was closed")
                self._receive_buffer.extend(data)
                for packet in self._extract_frames():
                    callback(packet)
        except (OrviboBinaryError, OSError, ssl.SSLError) as err:
            raise OrviboCaptureError(stage, err) from err
        finally:
            self.close()

    def close(self) -> None:
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
            self._socket = None

    def _connect(self) -> None:
        if not _CERT_PATH.is_file() or not _KEY_PATH.is_file():
            raise OrviboBinaryError("ORVIBO client certificate files are missing")

        # Require system-trusted server certificate AND matching server hostname.
        # Never fall back to an insecure connection, including legacy servers.
        context = ssl.create_default_context(purpose=ssl.Purpose.SERVER_AUTH)
        # The specific ORVIBO private CA has been corroborated against two
        # public source repositories and a captured server chain, but it is
        # not a WebPKI-trusted or independently manufacturer-authenticated CA.
        # Pin the exact CA DER fingerprint before it can be a trust anchor.
        if not _PINNED_SERVER_CA.is_file():
            raise OrviboBinaryError("ORVIBO pinned server CA is missing")
        pem = _PINNED_SERVER_CA.read_text(encoding="ascii")
        actual_hash = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
        if actual_hash != _PINNED_SERVER_CA_SHA256:
            raise OrviboBinaryError("ORVIBO pinned server CA fingerprint mismatch")
        context.load_verify_locations(cafile=str(_PINNED_SERVER_CA))
        # Preserve optional operator-supplied additional regional CAs.
        ca_file = _SERVER_CA_DIRECTORY / f"{self._host}.pem"
        if ca_file.is_file():
            context.load_verify_locations(cafile=str(ca_file))
        # ORVIBO's 2018 private CA has a non-critical Basic Constraints
        # extension. Recent Python/OpenSSL strict X.509 verification rejects
        # that legacy encoding despite a trusted pinned CA. Relax ONLY the
        # strict RFC-extension check, retaining certificate-chain verification,
        # trusted CA validation, expiry checks and DNS hostname verification.
        # Never set CERT_NONE or disable hostname checks.
        context.verify_flags &= ~ssl.VERIFY_X509_STRICT
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_cert_chain(_CERT_PATH, _KEY_PATH)

        raw_socket = socket.create_connection((self._host, _PORT), timeout=15)
        raw_socket.settimeout(15)
        try:
            self._socket = context.wrap_socket(raw_socket, server_hostname=self._host)
        except BaseException:
            raw_socket.close()
            raise

    def _next_serial(self) -> int:
        self._serial += 1
        return self._serial

    def _base_payload(self, command: int) -> dict[str, Any]:
        return {
            "cmd": command,
            "serial": self._next_serial(),
            "clientType": 1,
            "uniSerial": int(time.time() * 1000),
            "serverRecord": False,
            "ver": _CLIENT_VERSION,
            "debugInfo": f"Android_ZhiJia365_32_{_CLIENT_VERSION}",
        }

    @staticmethod
    def _encrypt(plaintext: bytes, key: bytes) -> bytes:
        return AES.new(key, AES.MODE_ECB).encrypt(pad(plaintext, AES.block_size))

    @staticmethod
    def _decrypt(ciphertext: bytes, key: bytes) -> bytes:
        return unpad(AES.new(key, AES.MODE_ECB).decrypt(ciphertext), AES.block_size)

    def _build_packet(self, payload: Mapping[str, Any], dynamic: bool = True) -> bytes:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        use_dynamic = dynamic and self._dynamic_key is not None
        key = self._dynamic_key if use_dynamic else _STATIC_KEY
        assert key is not None
        flag = b"dk" if use_dynamic else b"pk"
        encrypted = self._encrypt(raw, key)
        checksum = struct.pack(">I", zlib.crc32(encrypted) & 0xFFFFFFFF)
        session = self._session_id.encode("ascii")[:32].ljust(32, b"0")
        length = _HEADER_SIZE + len(encrypted)
        return b"hd" + struct.pack(">H", length) + flag + checksum + session + encrypted

    def _send(self, payload: Mapping[str, Any], dynamic: bool = True) -> None:
        if self._socket is None:
            raise OrviboBinaryError("ORVIBO binary socket is not connected")
        self._socket.sendall(self._build_packet(payload, dynamic=dynamic))

    def _decode_packet(self, packet: bytes) -> dict[str, Any] | None:
        if len(packet) < _HEADER_SIZE or packet[:2] != b"hd":
            return None
        encrypted = packet[_HEADER_SIZE:]
        if not encrypted or len(encrypted) % AES.block_size:
            return None
        expected_crc = struct.unpack(">I", packet[6:10])[0]
        if zlib.crc32(encrypted) & 0xFFFFFFFF != expected_crc:
            return None

        session = packet[10:42].decode("ascii", errors="ignore").strip("\x00")
        if session and session != "0" * 32:
            self._session_id = session.ljust(32, "0")[:32]

        for key in (self._dynamic_key, _STATIC_KEY):
            if key is None:
                continue
            try:
                value = json.loads(self._decrypt(encrypted, key).decode("utf-8"))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                return value
        return None

    def _extract_frames(self) -> list[dict[str, Any]]:
        packets: list[dict[str, Any]] = []
        while True:
            start = self._receive_buffer.find(b"hd")
            if start < 0:
                # Keep a possible split frame marker for the next socket read.
                if self._receive_buffer.endswith(b"h"):
                    self._receive_buffer[:] = b"h"
                else:
                    self._receive_buffer.clear()
                break
            if start:
                del self._receive_buffer[:start]
            if len(self._receive_buffer) < 4:
                break
            length = struct.unpack(">H", self._receive_buffer[2:4])[0]
            if length < _HEADER_SIZE:
                del self._receive_buffer[:2]
                continue
            if len(self._receive_buffer) < length:
                break
            frame = bytes(self._receive_buffer[:length])
            del self._receive_buffer[:length]
            decoded = self._decode_packet(frame)
            if decoded is not None:
                packets.append(decoded)
        return packets

    def _receive(self, timeout: float, idle_timeout: float = 0.5) -> list[dict[str, Any]]:
        if self._socket is None:
            raise OrviboBinaryError("ORVIBO binary socket is not connected")
        deadline = time.monotonic() + timeout
        last_data: float | None = None
        packets: list[dict[str, Any]] = []

        while time.monotonic() < deadline:
            if last_data is not None and time.monotonic() - last_data >= idle_timeout:
                break
            wait = min(0.25, max(0.0, deadline - time.monotonic()))
            readable, _, _ = select.select([self._socket], [], [], wait)
            if not readable:
                continue
            data = self._socket.recv(65536)
            if not data:
                break
            last_data = time.monotonic()
            self._receive_buffer.extend(data)
            received_packets = self._extract_frames()
            packets.extend(received_packets)
            if self._stop_commands and any(
                packet.get("cmd") in self._stop_commands
                for packet in received_packets
            ):
                break
        return packets

    def _receive_until_command(
        self,
        command: int,
        timeout: float,
        idle_timeout: float,
    ) -> list[dict[str, Any]]:
        """Receive packets until the requested response command arrives."""

        self._stop_commands = frozenset({command})
        try:
            return self._receive(timeout=timeout, idle_timeout=idle_timeout)
        finally:
            self._stop_commands = frozenset()

    def _handshake(self) -> list[dict[str, Any]]:
        payload = self._base_payload(0)
        payload.update(
            {
                "source": "ZhiJia365",
                "softwareVersion": "50206302",
                "sysVersion": "Android14_34",
                "hardwareVersion": "HomeAssistant",
                "language": "zh",
                "identifier": self._identifier,
                "phoneName": "Home Assistant",
            }
        )
        self._send(payload, dynamic=False)
        packets = self._receive_until_command(
            command=0,
            timeout=10,
            idle_timeout=_SESSION_RESPONSE_IDLE_TIMEOUT,
        )
        response = next(
            (packet for packet in packets if packet.get("cmd") == 0 and packet.get("key")),
            None,
        )
        if response is None:
            commands = [packet.get("cmd") for packet in packets]
            raise OrviboBinaryError(
                "ORVIBO binary handshake did not return a key "
                f"(packets={len(packets)}, commands={commands})"
            )
        self._dynamic_key = str(response["key"]).encode("utf-8")[:16]
        if len(self._dynamic_key) != 16:
            raise OrviboBinaryError("ORVIBO binary handshake returned an invalid key")
        session_id = response.get("sessionId")
        if isinstance(session_id, str) and session_id:
            self._session_id = session_id.ljust(32, "0")[:32]
        return packets

    def _login(self) -> list[dict[str, Any]]:
        payload = self._base_payload(2)
        payload.update(
            {
                "userName": self._email,
                "password": self._password_md5,
                "familyId": self._family_id,
                "type": 4,
                "needAccountDetailError": True,
            }
        )
        self._send(payload)
        packets = self._receive_until_command(
            command=2,
            timeout=10,
            idle_timeout=_SESSION_RESPONSE_IDLE_TIMEOUT,
        )
        response = next((packet for packet in packets if packet.get("cmd") == 2), None)
        if response is None:
            commands = [packet.get("cmd") for packet in packets]
            raise OrviboBinaryError(
                "ORVIBO binary login did not return a response "
                f"(packets={len(packets)}, commands={commands})"
            )
        if response.get("status") not in (None, 0, "0"):
            raise OrviboAuthenticationError(
                "ORVIBO binary login was rejected "
                f"(status={response.get('status')!r})"
            )
        return packets

    def _device_page_payload(self, page_index: int) -> dict[str, Any]:
        """Build the read-only device table request used by ZhiJia365."""

        payload = self._base_payload(147)
        payload.update(
            {
                "familyId": self._family_id,
                "pageIndex": page_index,
                "dataType": "all",
            }
        )
        if page_index:
            # Zero requests a complete table snapshot rather than an incremental sync.
            payload["lastUpdateTime"] = 0
        return payload

    def _query_device_page(self, page_index: int) -> list[dict[str, Any]]:
        self._send(self._device_page_payload(page_index))
        return self._receive(timeout=10, idle_timeout=2)

    def _query_online_status(self) -> list[dict[str, Any]]:
        payload = self._base_payload(230)
        payload["familyId"] = self._family_id
        self._send(payload)
        return self._receive(timeout=8, idle_timeout=2)

    def _control_payload(
        self,
        device_id: str,
        device_uid: str,
        order: str,
        value1: int,
        value2: int = 0,
        value3: int = 0,
        value4: int = 0,
        properties: Mapping[str, Any] | None = None,
        infrared: OrviboInfrared | None = None,
    ) -> dict[str, Any]:
        """Build the cmd=15 payload used by the current app for device control."""

        payload = self._base_payload(15)
        payload.update(
            {
                "uid": device_uid,
                "userName": self._email,
                "deviceId": device_id,
                "groupId": "",
                "order": order,
                "value1": value1,
                "value2": value2,
                "value3": value3,
                "value4": value4,
                "delayTime": 0,
                "qualityOfService": 1,
                "defaultResponse": 1,
                "propertyResponse": 0,
            }
        )
        if properties is not None:
            payload["properties"] = dict(properties)
        if is_tv_button_order(order):
            # IrButton -> control.a.irControl -> core.c.q0 uses a stored key
            # order, zero values/frequency/pulse count, and no pulse data.
            # Android JSONObject.put(name, null) omits that field.
            payload.pop("groupId", None)
            payload.pop("propertyResponse", None)
            payload.update(qualityOfService=0, freq=0, pluseNum=0)
        if infrared is not None:
            if order != "ir control" or not infrared.pulses:
                raise OrviboBinaryError("Invalid infrared command")
            payload.pop("groupId", None)
            payload.pop("propertyResponse", None)
            payload.update(
                freq=infrared.frequency,
                pluseNum=len(infrared.pulses),
                pluseData=",".join(str(duration) for duration in infrared.pulses),
            )
        return payload

    def _query_devices(self) -> list[dict[str, Any]]:
        """Download the complete paginated device table and online state."""

        packets: list[dict[str, Any]] = []
        seen_device_ids: set[str] = set()

        for page_index in range(_MAX_DEVICE_PAGES):
            page_packets = self._query_device_page(page_index)
            packets.extend(page_packets)

            page_device_ids = {
                device.uid for device in extract_devices(page_packets)
            }
            new_device_ids = page_device_ids - seen_device_ids
            seen_device_ids.update(page_device_ids)

            if page_index == 0:
                # The app requests host status between table metadata and page one.
                packets.extend(self._query_online_status())
                continue
            if not page_packets or not new_device_ids:
                break

        return packets


def discover_devices(
    host: str,
    email: str,
    password_md5: str,
    family_id: str,
) -> tuple[OrviboDevice, ...]:
    """Executor-friendly entry point for ORVIBO device discovery."""

    return OrviboBinaryClient(host, email, password_md5, family_id).discover()


def control_device(
    host: str,
    email: str,
    password_md5: str,
    family_id: str,
    device_id: str,
    device_uid: str,
    order: str,
    value1: int,
    value2: int = 0,
    value3: int = 0,
    value4: int = 0,
    properties: Mapping[str, Any] | None = None,
    infrared: OrviboInfrared | None = None,
) -> tuple[int | None, int | None, int | None, int | None]:
    """Send one device command through ORVIBO's mutual-TLS cloud socket."""

    return OrviboBinaryClient(
        host,
        email,
        password_md5,
        family_id,
    ).control_device(
        device_id,
        device_uid,
        order,
        value1,
        value2,
        value3,
        value4,
        properties,
        infrared,
    )
