# ORVIBO Cloud v1.4.1 — Blaupunkt LS 175 and BAXI swing

**Stable release candidate:** `v1.4.1` · **Date:** 14 November 2026 · **Previous release:** `v1.4.0`

## What's new

### Blaupunkt LS 175 / HomeMate IR speaker

The integration adds a user-selectable **Blaupunkt LS 175** infrared model for compatible virtual speakers (device type `7`, subtype `0`) routed through an Allone Pro. It is disabled by default and selected on the speaker's page inside the **existing complete configuration wizard**.

Physically verified NEC 38 kHz functions:

| Home Assistant entity | Code | Function |
| --- | --- | --- |
| Power **switch** | `0x00FFA25D` (07) | Relative power toggle |
| Vol + button | `0x00FFA857` (02) | Volume up |
| Vol − button | `0x00FF18E7` (03) | Volume down |
| Source button | `0x00FFE21D` (06) | Switch input |
| Equalizer button | `0x00FF38C7` (08) | Equalizer |
| Mute / BT Pair button | `0x00FF5AA5` (10) | Mute; pairing in BT mode |

**Important:** The Power switch does **not** read physical soundbar state. It uses the soundbar's single relative toggle command and an optimistic local estimate; external remote actions can desynchronize it. Use `switch.toggle` when an unconditional toggle is needed. No IR command is sent at startup. Unresponsive experimental codes 01/04/05/09 and the redundant LS175 IR test `remote` are not exposed; only those retired beta entity registrations are cleaned up on startup.

### BAXI Anori JSG35 horizontal swing

BAXI IR profile `7404` on Magic Cube now exposes **Off, Vertical, Horizontal and Both** in Home Assistant climate swing settings. It reuses the established 13-byte Electra/AUX-style encoder, and offline regression checks confirm distinct 212-duration/38 kHz outputs. Carlos confirmed horizontal-only louver movement previously using an experimental fork. A separate physical retest of horizontal-only with this v1.4.1 production build remains advisable.

### Daikin code provenance and licensing

The Daikin encoder's runtime/waveform code is unchanged. A source comparison found reset-byte constants matching upstream IRremoteESP8266 `IRDaikinESP::stateReset()`, so independent authorship of those elements cannot be established. The Daikin file is conservatively marked `SPDX-License-Identifier: LGPL-2.1-only` with upstream copyright notices; complete license text is included in the source and install archives. Other repository MIT files are not relicensed. See `PROVENANCE_AUDIT.md`, `THIRD_PARTY_NOTICES.md`, and `LICENSES/LGPL-2.1.txt`.

### Validated hub-disconnection behavior

A live test disconnected the maintainer's Allone Pro. ORVIBO initially continued reporting hub/IR children online, but subsequent cloud polling changed their `online` flags to false and Home Assistant made the Vivax climate `unavailable`. After reconnection, all returned online and Vivax recovered to `unknown` (available) **without restarting or reauthenticating**. The cloud-connectivity binary sensor stayed On throughout as expected. The exact cloud offline/online detection latency remains undetermined. No speculative heartbeat or automatic IR probe was introduced.

## Compatibility and unchanged behavior

- Existing integration domain and account settings; full cloud/TV/device/area/RF-blind options wizard preserved.
- Exact-profile Daikin 10502, Vivax/Midea 7579 (including tested Kaysun Swing), BAXI 7404 AC paths remain.
- Existing cloud/TLS binary transport, certificates, RF blinds, TV commands and cloud login behavior are unchanged from v1.4.0.
- Existing TV, blinds, lights and other virtual devices retain their established entity identity and behavior.
- The five retained Blaupunkt buttons keep their beta unique IDs. The old Power momentary button is replaced by the Power switch; update automations referencing the removed entity.

## Hardware-test scope and limitations

Carlos (@matexdj) physically tested Daikin and BAXI controls on the earlier **v1.4.0b1** ZIP, not separately on this production build. The maintainer physically tested the Vivax controls, Blaupunkt NEC commands, and Allone Pro availability transitions. Carlos's account did not provide a physical TV/blind/light regression test. See `VALIDATION.md` for details and the original [successful PR #5 CI run](https://github.com/Kosztyk/orvibo_cloud/actions/runs/43322696393); that run is **not** the CI result for v1.4.1.

## Installation / upgrade

**HACS:** Update ORVIBO Cloud to v1.4.1 after this GitHub release has been published, then restart Home Assistant.

**Manual:** Back up `/config/custom_components/orvibo_cloud`, replace the **entire** integration folder from `orvibo_cloud_v1.4.1_ha_install.zip`, and restart HA. Confirm version `1.4.1`.

The existing account/config entry is preserved. To activate Blaupunkt, open **ORVIBO Cloud → Configure**, select your speaker, select **Blaupunkt LS 175** on its individual settings page, and complete the rest of the wizard. Do not delete working device entities. To use BAXI Horizontal swing, choose Horizontal from its existing climate control.

## Release process

Source is published from a pinned v1.4.0 baseline using `scripts/publish_v1.4.1.sh`; **the archive alone does not update GitHub**. The publisher validates sources, then (when explicitly run with `--publish`) pushes to `main`, waits for main CI, tags `v1.4.1`, and waits for the tag-driven release workflow. A new stable release is not considered validated until the v1.4.1-specific GitHub Actions runs succeed.
