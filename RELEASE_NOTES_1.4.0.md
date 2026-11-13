# ORVIBO Cloud v1.4.0 — Native IR Climate Control

**Release date:** 2026-11-13
**GitHub tag:** `v1.4.0`
**Home Assistant integration domain:** `orvibo_cloud` (unchanged)

## Highlights

- Add native Home Assistant climate entities for three **exactly matched** HomeMate IR profiles:
  - **Daikin ARC433A87-compatible** — profile `10502`, Allone Pro hub type `67`.
  - **BAXI Anori JSG35** — profile `7404`, Magic Cube hub type `30`.
  - **Vivax / Midea 48-bit** — profile `7579`, Allone Pro hub type `67`.
- Generate IR control signals locally through the existing authenticated ORVIBO Cloud transport. **No HomeMate scenes or scene fallback** are used for any of these climate entities.
- Vivax/Midea: OFF, COOL, HEAT, AUTO, DRY and FAN_ONLY; 17–30 °C setpoints; Auto/Low/Medium/High fan; vertical swing via the **physically tested Kaysun/Midea `0xA202FFFFFF7E` special toggle**. The earlier standard Midea toggle `0xA201FFFFFF7C` did **not** move the maintainer's Vivax louvers.
- Use Home Assistant 2026.11 native climate temperature properties and config-entry-scoped device-registry APIs (`via_device_id`, scoped lookups). Preserve existing device/area selections and unique entity IDs.
- Maintain the v1.3.2 TLS trust configuration, credential handling, blind-state persistence, cloud polling and TV/RF remote features. The binary protocol, control transport, bundled PEM files and TLS verification settings are unchanged.
- Keep BAXI horizontal-only swing hidden until verified on physical hardware.

## Supported climate controls

| HomeMate remote | Hub | Modes | Temperature | Fan | Swing/presets |
| --- | --- | --- | --- | --- | --- |
| Daikin `10502` | Allone Pro (`67`) | Off, Auto, Cool, Heat, Dry, Fan only | 16–30 °C | Auto, Low, Medium, High | Vertical swing; ECO / Comfort combinations |
| BAXI `7404` | Magic Cube (`30`) | Off, Cool, Heat | 19–23 °C | Low, Medium, High | Vertical/Both; Turbo, Silence, iFeel, Display |
| Vivax/Midea `7579` | Allone Pro (`67`) | Off, Auto, Cool, Heat, Dry, Fan only | 17–30 °C | Auto, Low, Medium, High | Vertical swing toggle; no presets |

Entity creation is gated on exact remote type/subtype/profile ID, a compatible IR hub association and the configured device selection. Setup, discovery and polling do not transmit IR; control commands are sent only after explicit user actions.

## Physical test evidence and limits

- **Vivax `7579`:** The integration maintainer tested the generated Midea commands in Home Assistant and confirmed working mode, temperature and fan operation. They also confirmed that the **Kaysun/Midea** vertical Swing variant moves their physical unit. This is hardware evidence for that specific profile/model, **not** a guarantee for all Vivax or Midea models.
- **Daikin `10502` and BAXI `7404`:** The contributor to [PR #5](https://github.com/Kosztyk/orvibo_cloud/pull/5) reported physical testing of both units in the experimental integration. The upstream-derived implementation includes profile matching and offline tests; a separate independent hardware retest of every mode/preset in this published build is not claimed.
- **All IR climate entities use assumed state.** A cloud ACK is not physical feedback. Commands issued through the HomeMate phone app or physical remotes may desynchronize the displayed climate status.
- **Vivax Swing is a relative toggle.** Following restart or external operation, its actual louver position is unknown. Select Vertical first and verify movement; subsequent Off/Vertical commands toggle based on the integration's last acknowledged request.
- **Daikin / BAXI advanced presets and BAXI swing combinations** are profile-specific; avoid extrapolating their behavior to unrelated models.

## Installation and upgrade

For Home Assistant with HACS, upgrade ORVIBO Cloud to **v1.4.0** and restart Home Assistant. The integration domain and configuration entry are unchanged; existing RF blinds and TV entities should keep their identifiers and area assignments. Select the AC virtual remote in **ORVIBO Cloud → Configure** if it is not yet selected.

Manual installation: copy `custom_components/orvibo_cloud/` into `/config/custom_components/orvibo_cloud/` and restart. Back up the previous integration folder first. No new credentials, cloud server or HomeMate scenes are required.

## Validation and security

- Python compilation, static repository checks, protocol/encoder regression tests and Home Assistant registry migration tests are included. Full crypto/TLS tests require `pycryptodome` and are run in GitHub Actions, along with HACS and Hassfest.
- Real-device behavior is supported by the field tests above; CI does not connect to personal ORVIBO accounts.
- Existing authenticated binary TLS and bundled certificate material are unchanged from v1.3.2. No `CERT_NONE` or insecure fallback was introduced.
- The optional raw-event capture stream may be closed periodically by the server; it is not required for regular cloud or climate controls.

## Attribution

This release builds on the climate-control work contributed by **@matexdj** in [PR #5](https://github.com/Kosztyk/orvibo_cloud/pull/5), **merged into `main` on 2026-11-13**. The production release incorporates additional Home Assistant compatibility work, a physically tested Vivax/Midea encoder, and intentionally restores the v1.3.2 binary/control implementation rather than retaining the PR's unverified stored-AC-OFF envelope. We also acknowledge the protocol descriptions in **IRremoteESP8266**, with licensing and provenance notes in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Original ORVIBO Cloud upstream: `maycode0-0/orvibo-cloud`; existing MIT license notices retained.

## Reconciliation with merged PR #5

The release source was reviewed after GitHub `main` advanced to merge commit `a3b93d1`. The publishing script refuses any other base SHA. On top of the merged PR, it installs the maintainer-tested release source, including the Kaysun/Midea Swing command. `binary.py`, `control.py`, and all three bundled TLS files are verified against the v1.3.2 tag/commit. This intentionally drops the PR's unverified special stored-AC-OFF command handling while retaining validated climate routing and controls.
