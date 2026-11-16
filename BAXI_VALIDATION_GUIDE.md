# BAXI Anori JSG35 validation

ORVIBO Cloud v1.4.2 exposes Heat and Cool at **16–32 °C**, three fan speeds and four swing modes on HomeMate virtual AC profile `7404` with a Magic Cube (`30`). The 13-byte Electra/AUX-style encoder produces 212 pulse durations and a 38 kHz carrier.

Carlos (@matexdj) confirmed that Horizontal moved only the horizontal louvers using the `1.4.1b9` build on Home Assistant OS 18.4 and Core 2026.11.1. He previously confirmed Off, Vertical and Both, Heat/Cool at 19–23 °C, the three fan speeds, Turbo, Silence, iFeel and Display on `1.4.0b1`. iFeel and Display send IR commands. [Contributor test reports](https://github.com/Kosztyk/orvibo_cloud/pull/5)

## Temperature coverage

The original remote displays 16–32 °C in both Heat and Cool. Offline tests cover all 408 combinations of 17 whole-degree setpoints, two modes, three fan speeds and four swing modes. Physical testing of integration commands outside 19–23 °C is pending.

## Physical checks

1. Confirm that the virtual AC uses profile `7404` and that its Magic Cube is online in HomeMate.
2. Use the Home Assistant climate entity to select Heat or Cool and a test setpoint. Compare the resulting mode and displayed setpoint with the requested values.
3. Check the newly exposed values on the physical unit, with particular attention to 16, 31 and 32 °C in both modes.
4. Verify Off, Vertical, Horizontal and Both visually. Horizontal should move only the horizontal louvers.
5. Record the Home Assistant version, integration version, hub type, requested mode and setpoint, displayed setpoint, fan/swing response and any error.

[Release validation](VALIDATION.md) · [Protocol provenance](THIRD_PARTY_NOTICES.md)
