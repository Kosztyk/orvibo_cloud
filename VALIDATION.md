# Validation — ORVIBO Cloud v1.4.0

## CI gates

The `Validate ORVIBO Cloud` workflow runs on pushes and pull requests, including the production main-branch push:

- Static repository/HACS packaging check: `python tools/check_repository.py`
- `pycryptodome==3.23.0` installation and all unittest modules: `python -m unittest discover -s tests -v`
- Python bytecode compilation of the integration.
- HACS validation using `hacs/action@main`.
- Home Assistant Hassfest validation using `home-assistant/actions/hassfest@master`.

The tag-publishing workflow also checks version/tag agreement, runs packaging, unit tests and Python compilation before creating the full GitHub Release. The included publishing script waits for the main-branch validation run to pass **before** pushing `v1.4.0`.

## Hardware observations

- **Vivax/Midea `7579` and Allone Pro:** The maintainer tested the beta's generated Midea 48-bit mode, temperature and fan commands, and physically confirmed the alternative Kaysun/Midea vertical swing toggle after the standard Midea variant failed. The stable release preserves that packet. State remains assumed.
- **Daikin `10502` / Allone Pro and BAXI `7404` / Magic Cube:** The contributor of merged PR #5 reported physical response on the experimental integration. This is distinct from an independent physical test of every feature of the released source tree.
- The existing cloud login, TV control and RF blinds were exercised during previous maintainer testing; v1.4.0 does not change the original binary transport or TLS bundle.

## Scope and limitations

No offline test proves that a specific physical appliance accepted a new IR command. Home Assistant does not receive actual AC operating state from ORVIBO. Vertical swing for Vivax is a relative toggle; first action after external changes can be ambiguous.

The bundled ORVIBO client certificate/key and pinned legacy CA are unchanged from v1.3.2 and were previously tested for certificate chain, DNS hostname and rejected-login behavior. No TLS-verification bypass has been introduced.

If the validation workflow reports a failure or HACS/Hassfest incompatibility, **do not publish the release tag** until resolved.

## Local checks

```bash
python3 -m pip install pycryptodome==3.23.0
python3 tools/check_repository.py
python3 -m unittest discover -s tests -v
python3 -m compileall -q custom_components
```

These commands require a Python interpreter compatible with the integration and OpenSSL for locally generated TLS test certificates.
