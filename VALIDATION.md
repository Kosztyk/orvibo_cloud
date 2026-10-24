# Validation status and limitations

## Automated checks for v1.3.2

The GitHub Actions workflow `.github/workflows/validate.yml` runs:

- **HACS Validation** using `hacs/action@main`, with category `integration`
  and no ignored checks.
- **Hassfest Validation** using `home-assistant/actions/hassfest@master`.
- **Packaging and Python checks** for manifest structure, HACS metadata,
  repository layout, version formatting, and Python compilation, plus TLS and
  listener regression tests. The suite contains 16 tests.

For local verification, run:

```bash
python3 -m pip install pycryptodome==3.23.0
python3 tools/check_repository.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q custom_components
```

The packaging and reviewer checks are static. The security tests exercise the
actual binary client against a local TLS server with temporary certificates:
the legacy non-critical CA extension works, while a wrong hostname, an
untrusted certificate chain, and a changed pinned CA fail. Listener tests
verify that login rejection ends retries and network failures back off from
5 to 300 seconds. OpenSSL is required to generate the temporary test certificates.

These tests do **not** exercise Home Assistant against a live ORVIBO cloud
account, test actual RF blind commands, or validate real-world device behavior.

## Historical runtime tests

The integration README previously stated that 51 runtime tests passed against
Home Assistant 2026.10.2. That test suite is not included in the current public
GitHub tree; this release does not claim to have reproduced those results.

## Sensitive data

Never disclose ORVIBO account credentials, authentication tokens, personally
identifying data or private device identifiers in public GitHub reports. Redact
logs and diagnostics before sharing. The existing bundled ORVIBO client TLS
credential files are unchanged in this packaging update and should be assessed
separately for suitability of public distribution.

## v1.3.2 review evidence

The maintainer has reported that open/close/stop controls work using the locally tested v1.3.2 build with the legacy ORVIBO CA chain pinned and hostname verification enabled. This is real-device user validation; GitHub Actions cannot authenticate to their personal cloud account. Legacy CA trust is supported by two independent integration projects, not a manufacturer-authenticated statement.

The CA has a non-critical Basic Constraints extension rejected by OpenSSL strict X.509 validation, so the binary socket clears only `VERIFY_X509_STRICT`. Signature chain validation, certificate validity checks and hostname verification remain mandatory. No insecure fallback is provided.
