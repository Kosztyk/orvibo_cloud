# Changelog

## 1.3.2 — HACS reviewer fixes

1. **Authenticated TLS:** port 10002 uses hostname checks and `ssl.CERT_REQUIRED` with the ORVIBO private CA bundled and fingerprint checked before loading it. The server trust anchor was corroborated against two public ORVIBO integration repositories and a certificate chain observed on the user's server. The CA is self-signed and its authenticity has not been confirmed by ORVIBO directly. `VERIFY_X509_STRICT` alone is relaxed because this 2018 CA has non-critical Basic Constraints; ordinary certificate-chain, validity and DNS hostname verification remain enabled. There is no `CERT_NONE` fallback.
2. **Account privacy:** diagnostic export redacts `CONF_EMAIL` in addition to password hash and user ID.
3. **Area persistence:** initial device registration applies configured areas; polling no longer overwrites manual Home Assistant area assignments. An explicit options-flow change still updates the area.
4. **English translations:** `translations/en.json` now matches `strings.json`.
5. **Capture reconnects:** rejected binary login ends the capture listener; transient network errors back off exponentially from five seconds to five minutes.

The tested integration's protocol, device controls and remembered blind-state logic are otherwise unchanged. Live device operation was confirmed by the integration maintainer on the local test build; CI cannot reproduce a real ORVIBO device connection.

## 1.3.1 — HACS publication preparation

- Add HACS and Hassfest GitHub Actions validation with no skipped HACS checks.
- Add offline packaging checks and Python syntax validation.
- Add GitHub Actions publishing workflow for the 1.3.1 release, guarded by
  successful validation on the main branch.
- Align root and integration README documentation, including HACS installation
  and the optional per-blind remembered-state feature.
- Clarify that earlier claimed hardware/runtime tests are not bundled.
- Make the HACS display name human-readable and add the integration type.

**No runtime device control, login, network protocol, TLS or blind logic changed.**
