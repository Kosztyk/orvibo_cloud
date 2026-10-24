# ORVIBO Cloud v1.3.2 — HACS reviewer corrections

Addresses Frenck's feedback on https://github.com/hacs/default/pull/12441.

1. **Authenticated TLS:** port 10002 uses hostname checks and `ssl.CERT_REQUIRED` with the ORVIBO private CA bundled and fingerprint checked before loading it. The server trust anchor was corroborated against two public ORVIBO integration repositories and a certificate chain observed on the user's server. The CA is self-signed and its authenticity has not been confirmed by ORVIBO directly. `VERIFY_X509_STRICT` alone is relaxed because this 2018 CA has non-critical Basic Constraints; ordinary certificate-chain, validity and DNS hostname verification remain enabled. There is no `CERT_NONE` fallback.
2. **Account privacy:** diagnostic export redacts `CONF_EMAIL` in addition to password hash and user ID.
3. **Area persistence:** initial device registration applies configured areas; polling no longer overwrites manual Home Assistant area assignments. An explicit options-flow change still updates the area.
4. **English translations:** `translations/en.json` now matches `strings.json`.
5. **Capture reconnects:** rejected binary login ends the capture listener; transient network errors back off exponentially from five seconds to five minutes.

The tested integration's protocol, device controls and remembered blind-state logic are otherwise unchanged. Live device operation was confirmed by the integration maintainer on the local test build; CI cannot reproduce a real ORVIBO device connection.

Validation includes HACS with no ignored checks, Hassfest, Python compilation,
and 16 packaging/security regression tests. The security tests perform local
TLS handshakes and check rejected-login handling and bounded network backoff.
