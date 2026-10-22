# Validation status and limitations

## Automated checks for v1.3.1

The GitHub Actions workflow `.github/workflows/validate.yml` runs:

- **HACS Validation** using `hacs/action@main`, with category `integration`
  and no ignored checks.
- **Hassfest Validation** using `home-assistant/actions/hassfest@master`.
- **Packaging and Python checks** for manifest structure, HACS metadata,
  repository layout, version formatting, and Python compilation.

For local verification, run:

```bash
python3 tools/check_repository.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q custom_components
```

The packaging tests are static checks. They do **not** exercise Home Assistant
against a live ORVIBO cloud account, verify authentication, test actual RF blind
commands, or validate real-world device behavior.

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
