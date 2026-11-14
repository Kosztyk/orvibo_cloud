# BAXI Anori JSG35 — v1.4.1 swing validation

This release exposes **Off, Vertical, Horizontal, Both** swing on HomeMate virtual AC profile `7404` using a Magic Cube (`30`). The existing BAXI Electra/AUX-style encoder builds a 13-byte state, 212 pulse durations and a 38 kHz carrier. The four swing modes produce distinct output vectors in the offline tests.

Carlos (@matexdj) previously reported that Horizontal moved only horizontal louvers with his experimental fork. His v1.4.0b1 physical test confirmed Off, Vertical and Both, but Horizontal was excluded from that beta's UI. **A retest of Horizontal in the exact v1.4.1 release is still recommended**; distinct output vectors alone cannot prove physical actuation.

## Suggested supervised test

1. Select the correct BAXI virtual AC and its matching Magic Cube in HomeMate. Confirm the model and that the cloud-reported hub is online.
2. Turn on the AC using the normal climate entity at a safe target temperature.
3. Select each swing mode in turn, observing actual louver movement: Off, Vertical, Horizontal, Both.
4. Confirm Horizontal moves only the horizontal louvers and that returning to Off stops movement. Capture model/firmware details if behavior differs.
5. Avoid remote command floods, arbitrary cloud order probes or background IR polling.

The contributor also confirmed Heat, Cool, Off, three fan speeds, Turbo, Silence, iFeel and Display in v1.4.0b1. Do not interpret the iFeel command as an actual HA temperature sensor. Full provenance and licensing references are available in `THIRD_PARTY_NOTICES.md` and `PROVENANCE_AUDIT.md`.
