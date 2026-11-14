"""Offline Blaupunkt LS 175 NEC vectors transcribed from the user-supplied RCoid RCF.

These are *test* codes, not a verified compatibility claim for ORVIBO type-7.
The ten RCF signal strings all use 38 kHz, 342/171 carrier-period
leader timings, 21 mark periods and 21/64 space periods; they each
contain 32 NEC bits. Hex values below are their on-wire MSB-first words.
Button meanings are now primarily taken from physical LS 175 testing.
The serialized RCoid graphic/label ordering is not a reliable button map;
unknown buttons stay numbered and their NEC words stay unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass

from .control import OrviboControlCommand, OrviboInfrared


@dataclass(frozen=True, slots=True)
class LS175TestKey:
    key: str
    label: str
    nec_word: int
    identified: bool = False


# Order is the order of the ten 38kHz waveforms in "Blaupunkt LS 175.rcf".
# Physical testing of the v1.4.1b2 buttons corrected the RCF label offsets.
# Keep the exact code_01...code_10 identities and hexadecimal words stable
# across upgrades, so existing HA entities and scripts never change behavior.
LS175_TEST_KEYS: tuple[LS175TestKey, ...] = (
    LS175TestKey("code_01", "Test Code 01", 0x00FF9867),
    LS175TestKey("code_02", "Vol +", 0x00FFA857, True),
    LS175TestKey("code_03", "Vol -", 0x00FF18E7, True),
    LS175TestKey("code_04", "Test Code 04", 0x00FF827D),
    LS175TestKey("code_05", "Test Code 05", 0x00FFC23D),
    LS175TestKey("code_06", "Source", 0x00FFE21D, True),
    LS175TestKey("code_07", "Power Toggle", 0x00FFA25D, True),
    LS175TestKey("code_08", "Equalizer", 0x00FF38C7, True),
    LS175TestKey("code_09", "Test Code 09 (no response)", 0x00FF10EF),
    LS175TestKey("code_10", "Mute / BT Pair", 0x00FF5AA5, True),
)

# Only physically verified functions receive Home Assistant button entities.
# Unknown/no-response IR definitions are retained for offline comparisons.
LS175_CONFIRMED_KEYS: tuple[LS175TestKey, ...] = tuple(
    key for key in LS175_TEST_KEYS if key.identified
)

_KEYS = {key.key: key for key in LS175_TEST_KEYS}

# Optional named commands for scripts and remote.send_command. They are
# aliases of the already-tested numbered RCF vectors, not new IR waveforms.
# Code 10 is context-sensitive: it mutes outside Bluetooth mode, but can
# initiate Bluetooth pairing when the soundbar is in Bluetooth mode.
LS175_COMMAND_ALIASES: dict[str, str] = {
    "power_toggle": "code_07",
    "volume_up": "code_02",
    "volume_down": "code_03",
    "source": "code_06",
    "mute": "code_10",
    "bluetooth_pair": "code_10",
    "equalizer": "code_08",
}


def ls175_nec_pulses(word: int) -> tuple[int, ...]:
    """Convert an RCoid 32-bit on-wire NEC word to microsecond pulses.

    The RCoid file measures 342, 171, 21 and 64 carrier periods at 38kHz,
    equivalent to 9000, 4500, ~553 and ~1684 microseconds. We send nominal
    NEC 560/1680 timings, with a 1000us final gap instead of RCoid's 1-cycle
    end marker, consistent with ORVIBO's existing raw IR frame format.
    """
    if type(word) is not int or not 0 <= word <= 0xFFFFFFFF:
        raise ValueError("Invalid NEC word")
    address = (word >> 24) & 0xFF
    inverted_address = (word >> 16) & 0xFF
    command = (word >> 8) & 0xFF
    inverted_command = word & 0xFF
    if (address ^ inverted_address) != 0xFF or (command ^ inverted_command) != 0xFF:
        raise ValueError("Invalid NEC complement bytes")
    pulses = [9000, 4500]
    for shift in range(31, -1, -1):
        pulses.extend((560, 1680 if word & (1 << shift) else 560))
    pulses.extend((560, 1000))
    return tuple(pulses)


def ls175_test_command(name: str) -> OrviboControlCommand:
    """Build one user-initiated raw IR command with no scene or stored-key mode."""
    if not isinstance(name, str):
        raise ValueError("Unsupported LS175 test command")
    canonical = LS175_COMMAND_ALIASES.get(name, name)
    if canonical not in _KEYS:
        raise ValueError("Unsupported LS175 test command")
    pulses = ls175_nec_pulses(_KEYS[canonical].nec_word)
    return OrviboControlCommand(
        "ir control", 0, infrared=OrviboInfrared(38000, pulses)
    )


def is_ls175_test_target(device: object, devices: object) -> bool:
    """Require type-7/subtype-0 remote and exactly one Allone Pro route.

    ORVIBO device UID is the target; shared cloud_uid identifies the hub.
    Brand names and the common hardware model hash are NOT unique IDs.
    """
    if (
        getattr(device, "device_type", None) != "7"
        or getattr(device, "sub_device_type", None) != "0"
        or not getattr(device, "uid", None)
        or not getattr(device, "cloud_uid", None)
        or not getattr(device, "model", None)
        or getattr(device, "online", None) is False
    ):
        return False
    hubs = [
        hub for hub in devices
        if hub.device_type == "67"
        and hub.cloud_uid == device.cloud_uid
        and hub.model == device.model
        and hub.online is not False
    ]
    return len(hubs) == 1
