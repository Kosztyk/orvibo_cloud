"""Midea 48-bit infrared frame encoder for Vivax/HomeMate profile 7579.

Protocol reference: IRremoteESP8266 src/ir_Midea.{h,cpp} (LGPL-2.1).
The algorithm is independently written in Python based on the protocol fields,
encoder and checksum reference. The Vivax hardware commands were field-tested by the integration maintainer.

Normal state commands consist of a 48-bit frame and its bitwise inverse.
Midea vertical swing is a standalone *toggle*, not an absolute state bit.
"""

from __future__ import annotations

from dataclasses import dataclass

MIDEA_FREQUENCY = 38000
MIDEA_FRAME_BITS = 48
MIDEA_MASK = (1 << MIDEA_FRAME_BITS) - 1
# Vivax 7579: physically tested Kaysun/Midea vertical swing toggle.
# The same special frame may activate Econo on unrelated Midea models, so do
# not generalize this value to other IR profiles.
MIDEA_SWING_V_TOGGLE = 0xA202FFFFFF7E
MIDEA_MODES = {"cool": 0, "dry": 1, "auto": 2, "heat": 3, "fan_only": 4}
MIDEA_FANS = {"auto": 0, "low": 1, "medium": 2, "high": 3}
MIDEA_MIN_TEMP = 17
MIDEA_MAX_TEMP = 30

@dataclass(frozen=True, slots=True)
class Midea48Signal:
    frequency: int
    pulses: tuple[int, ...]
    frame: int


def _reverse_byte(value: int) -> int:
    """Reverse the bit order in an 8-bit value, matching IRremoteESP8266."""
    return int(f"{value & 255:08b}"[::-1], 2)


def midea48_checksum(frame: int) -> int:
    """Checksum of the five bytes ABOVE the trailing 8-bit checksum."""
    if type(frame) is not int or not 0 <= frame <= MIDEA_MASK:
        raise ValueError("Midea frame must be a 48-bit unsigned integer")
    checksum_sum = sum(_reverse_byte((frame >> shift) & 255) for shift in (8,16,24,32,40))
    return _reverse_byte(-checksum_sum & 255)


def midea48_state(*, power: bool, mode: str, temperature: int, fan: str) -> int:
    """Generate a complete 48-bit normal state command, no learned scenes.

    The reference state 0xA1826FFFFF62 is 25 C in Fahrenheit mode. Set the
    Celsius flag and use the 17 C offset without touching reserved fields.
    """
    if type(power) is not bool or mode not in MIDEA_MODES:
        raise ValueError("Unsupported Midea power or mode")
    if type(temperature) is not int or not MIDEA_MIN_TEMP <= temperature <= MIDEA_MAX_TEMP:
        raise ValueError("Midea temperature must be an integer from 17 to 30 C")
    if fan not in MIDEA_FANS:
        raise ValueError("Unsupported Midea fan speed")
    b = bytearray.fromhex("a1 82 6f ff ff 62")
    # Byte 4: Power bit7, fan bits3-4, HVAC mode bits0-2.
    b[1] = (0x80 if power else 0) | (MIDEA_FANS[fan] << 3) | MIDEA_MODES[mode]
    # Byte 3: preserve reserved bit6; clear Fahrenheit bit5; Temp bits0-4.
    b[2] = 0x40 | (temperature - MIDEA_MIN_TEMP)
    frame = int.from_bytes(b, "big") & ~255
    return frame | midea48_checksum(frame)


def midea48_pulses(frame: int) -> tuple[int, ...]:
    """4480/4480 header + 48 bits MSB-first, then 48 inverted bits.

    Midea sends the full frame followed by its inverse, not a duplicate.
    Each half contains 100 alternating mark/space durations.
    """
    if type(frame) is not int or not 0 <= frame <= MIDEA_MASK:
        raise ValueError("Midea frame must be a 48-bit unsigned integer")
    pulses: list[int] = []
    for value in (frame, frame ^ MIDEA_MASK):
        pulses.extend((4480, 4480))
        for byte in value.to_bytes(6, "big"):
            for bit in range(7, -1, -1):
                pulses.extend((560, 1680 if byte & (1 << bit) else 560))
        pulses.extend((560, 5600))
    return tuple(pulses)


def midea48_signal(*, power: bool, mode: str, temperature: int, fan: str) -> Midea48Signal:
    frame = midea48_state(power=power, mode=mode, temperature=temperature, fan=fan)
    return Midea48Signal(MIDEA_FREQUENCY, midea48_pulses(frame), frame)


def midea48_swing_toggle_signal() -> Midea48Signal:
    """Encode the Vivax-tested Kaysun/Midea swing toggle (profile 7579 only)."""
    return Midea48Signal(MIDEA_FREQUENCY,
                         midea48_pulses(MIDEA_SWING_V_TOGGLE),
                         MIDEA_SWING_V_TOGGLE)
