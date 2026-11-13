# Changelog

## 1.4.0 — 2026-11-13

- Add exact-profile cloud IR climate support for Daikin (10502), BAXI (7404), and Vivax/Midea (7579), derived from PR #5 and subsequent maintainer testing.
- Native Midea 48-bit encoding for Vivax, including the physically tested Kaysun/Midea vertical swing toggle `0xA202FFFFFF7E`. No HomeMate scene dependencies or fallback.
- Support full-state climate mode, temperature and fan commands; profile-specific swing/preset features; report only the last acknowledged requested (assumed) state.
- Migrate deprecated Home Assistant device-registry APIs and native climate temperature properties for HA 2026.11.
- Hide unverified BAXI horizontal-only swing; preserve original verified binary TLS transport, client credentials, and existing blinds/TV device control behavior.
- Add protocol regression tests, contributor credit, release notes and automated tag publishing.

## 1.3.2 — 2026-10-24

- Authenticate ORVIBO port-10002 TLS using pinned bundled CA and DNS hostname verification; relax only the OpenSSL X.509 strict flag required by the legacy CA.
- Redact diagnostics account email, preserve manually assigned HA areas, synchronize English translations, and bound raw-capture reconnects.

## 1.3.1 — 2026-10-22

- Prepare HACS and Hassfest validation, manifest metadata, and repository structure.
- Document RF blind assumed-state persistence and restoration.

See `RELEASE_NOTES_1.4.0.md` and `RELEASE_NOTES_1.3.2.md` for details.
