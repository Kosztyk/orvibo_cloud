# Blaupunkt LS 175 — ORVIBO Cloud v1.4.1

## Eligibility and setup

The HomeMate virtual speaker must be type `7` / subtype `0`, selected in ORVIBO Cloud, and routed to one compatible online Allone Pro. Open **Settings → Devices & services → ORVIBO Cloud → Configure** and complete the original wizard: cloud/TV/diagnostics → device selection → each selected device's area and RF settings. On the eligible soundbar page choose **Speaker infrared model → Blaupunkt LS 175** (None by default). Finish every page to save the selection.

## Hardware-verified IR mapping

| Visible HA entity | NEC word | Original test code | Result |
| --- | --- | --- | --- |
| Power `switch` | `0x00FFA25D` | 07 | Physical On/Off **toggle** |
| Vol + `button` | `0x00FFA857` | 02 | Volume up |
| Vol − `button` | `0x00FF18E7` | 03 | Volume down |
| Source `button` | `0x00FFE21D` | 06 | Change input |
| Equalizer `button` | `0x00FF38C7` | 08 | Change EQ |
| Mute / BT Pair `button` | `0x00FF5AA5` | 10 | Mute; pairing in Bluetooth mode |

Codes `01 = 0x00FF9867`, `04 = 0x00FF827D`, `05 = 0x00FFC23D`, `09 = 0x00FF10EF` produced no observed response. They remain in the offline decoder but do not appear as functional Home Assistant entities. The old LS175 IR test remote and obsolete beta buttons are intentionally retired and cleaned up narrowly; the five known buttons retain stable unique IDs.

## Power state limitation

Only one NEC power toggle word exists for this working soundbar, not distinct `POWER_ON` and `POWER_OFF` codes. The Home Assistant Power switch tracks a **local estimated state**; an external remote, HomeMate action or unplug may make it wrong. `switch.toggle` always sends one power toggle, while `turn_on`/`turn_off` consult that estimate. The integration cannot truthfully confirm physical power state, and no automatic command is sent on startup.

## Troubleshooting and rollback

- A missing entity: check speaker selection, complete every options wizard screen, check the model opt-in and cloud-reported hub online status.
- A command that doesn't work: check the actual soundbar input mode and physical IR path; an ORVIBO command ACK is not a physical reception confirmation.
- A switch out of sync: use `switch.toggle` intentionally and verify physical response; the integration cannot read back the real state.
- For rollback, back up and replace `/config/custom_components/orvibo_cloud` with your previous complete directory, restart HA, and remember that retired beta entities/automations might need to be recreated manually.
