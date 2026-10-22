# Changelog

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
