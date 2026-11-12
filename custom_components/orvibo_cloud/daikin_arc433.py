"""Experimental ARC433A87-compatible candidate based on IRremoteESP8266 DAIKIN.

The DAIKIN 280-bit OFF signal was physically confirmed with Sala Matex.
Ported from the local v0.6 patch for use in the shared climate integration.
No network or Home Assistant dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib

FREQUENCY_HZ = 38000
OFF_23_HEAT_SHA256 = "584c9f76d0aea0da52e97435daaa1cacc41642f26fdf5b04b3fd8d4e1a7e6b0e"
HVAC_CODES = {"auto": 0, "dry": 2, "cool": 3, "heat": 4, "fan_only": 6}
FAN_CODES = {"auto": 10, "low": 3, "medium": 5, "high": 7}


@dataclass(frozen=True)
class Signal:
    state: bytes
    pulses: tuple[int, ...]
    frequency: int = FREQUENCY_HZ


def daikin_signal(*, power: bool, temperature: int = 23, mode: str = "heat",
                  fan: str = "auto", eco: bool = False, comfort: bool = False,
                  swing_v: bool = False, swing_h: bool = False) -> Signal:
    if type(power) is not bool:
        raise ValueError("power must be a bool")
    if type(temperature) is not int or not 16 <= temperature <= 30:
        raise ValueError("temperature must be an integer between 16 and 30 Celsius")
    if mode not in HVAC_CODES or fan not in FAN_CODES:
        raise ValueError("unsupported mode or fan setting")
    if any(type(flag) is not bool for flag in (eco, comfort, swing_v, swing_h)):
        raise ValueError("eco, comfort and swing settings must be boolean")
    state = bytearray(35)
    defaults = {
        0: 0x11, 1: 0xDA, 2: 0x27, 4: 0xC5,
        8: 0x11, 9: 0xDA, 10: 0x27, 12: 0x42,
        16: 0x11, 17: 0xDA, 18: 0x27, 21: 0x49,
        22: 0x1E, 24: 0xB0, 27: 0x06, 28: 0x60, 31: 0xC0,
    }
    for i, val in defaults.items():
        state[i] = val
    state[6] = (state[6] & ~0x10) | (0x10 if comfort else 0)
    state[21] = (state[21] & ~0x71) | (int(power) | (HVAC_CODES[mode] << 4))
    state[22] = temperature * 2
    state[24] = (FAN_CODES[fan] << 4) | (0x0F if swing_v else 0)
    state[25] = 0x0F if swing_h else 0
    state[32] = (state[32] & ~0x04) | (0x04 if eco else 0)
    for start, end in ((0, 8), (8, 16), (16, 35)):
        state[end - 1] = sum(state[start : end - 1]) & 0xFF

    # Serialize exactly as the verified IRDaikinESP sendDaikin() method.
    pulses = []
    for _ in range(5):
        pulses.extend((428, 428))
    pulses.extend((428, 29428))
    for start, end in ((0, 8), (8, 16), (16, 35)):
        pulses.extend((3650, 1623))
        for value in state[start:end]:
            for shift in range(8):
                pulses.extend((428, 1280 if (value & (1 << shift)) else 428))
        pulses.extend((428, 29428))
    if len(pulses) != 584:
        raise ValueError("Invalid Daikin packet length")
    return Signal(bytes(state), tuple(pulses))


def self_check() -> None:
    """The previously successful OFF signal must be bit-for-bit unchanged."""
    result = daikin_signal(power=False)
    sha = hashlib.sha256(",".join(map(str, result.pulses)).encode()).hexdigest()
    if sha != OFF_23_HEAT_SHA256:
        raise ValueError("Known-good OFF pulse reference changed: aborting")
    if result.state.hex() != (
        "11da2700c50000d711da270042000054"
        "11da270000482e00a0000006600000c000004e"
    ):
        raise ValueError("Known-good OFF state reference changed: aborting")


self_check()
