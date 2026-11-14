# Changelog

## 1.4.1 — 2026-11-14

- Promote the user-tested local v1.4.1b9 branch as a stable release candidate without changing cloud/TLS transport, Vivax/Midea encoder, original climate runtime, TV, blinds or home configuration wizard.
- Add opt-in Blaupunkt LS 175 infrared controls for eligible HomeMate speaker devices: **Power switch** (NEC Code 07), **Vol +**, **Vol −**, **Source**, **Equalizer** and **Mute / BT Pair**. Preserve five button unique IDs and clean only superseded experimental entity registrations.
- Expose all **four BAXI 7404 swing modes**: Off, Vertical, Horizontal and Both, using the existing Electra/AUX 13-byte encoder. Four distinct 212-duration waveforms verified offline; horizontal-only was physically confirmed in the contributor's experimental fork, not separately on this production candidate.
- Fix the original soundbar options-flow crash, maintain per-device model opt-in and restore the entire established settings wizard (cloud/TV, device selection, areas and RF-blind settings).
- Add conservative LGPL-2.1-only attribution and license text for Daikin encoder; document code-provenance comparison with IRremoteESP8266 without asserting clean-room origin.
- Document contributor hardware coverage and the maintainer's physical Allone Pro unplug/replug results. Availability correctly follows the cloud-reported hub status once that status updates; detection can be delayed by cloud-side caching.
- Update README, release notes, validation, provenance, deployment guide and regression tests for v1.4.1. No automatic IR is sent by setup or polling.

## 1.4.0 — 2026-11-13

- Add exact-profile cloud IR climate support for Daikin (10502), BAXI (7404), and Vivax/Midea (7579), building on @matexdj's PR #5 and the maintainer's Vivax testing.
- Native Midea 48-bit encoding and physically tested Kaysun/Midea vertical swing `0xA202FFFFFF7E`, with no scene fallback.
- Home Assistant 2026.11 native climate properties and registry compatibility, assumed state tracking and profile-specific commands.
- Initially restrict BAXI horizontal-only swing pending the contributor's physical test follow-up.
- Preserve the verified TLS binary transport and existing TV/blind behavior; add CI, HACS, Hassfest and release workflows.

## 1.3.2 — 2026-10-24

- Verify TLS using a pinned legacy CA and hostname validation, redact account diagnostics, preserve manually assigned areas and constrain raw-event capture retries.

## 1.3.1 — 2026-10-22

- Prepare HACS and Hassfest validation and document RF blind state persistence.

See `RELEASE_NOTES_1.4.1.md` and `RELEASE_NOTES_1.4.0.md` for details.
