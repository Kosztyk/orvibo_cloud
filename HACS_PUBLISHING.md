# Publishing ORVIBO Cloud v1.4.0

The [ORVIBO Cloud HACS default-catalog PR #12441](https://github.com/hacs/default/pull/12441) has been merged. You do **not** need to submit a duplicate HACS/default PR for v1.4.0; HACS discovers official GitHub releases.

## Automated publisher

The complete production source archive contains `scripts/publish_v1.4.0.sh`. On a Mac/Linux workstation with Git, Python 3.13+, rsync and an authenticated GitHub CLI (`gh`):

```bash
unzip orvibo_cloud_v1.4.0_after_PR5_merge_full_source.zip
cd orvibo_cloud_v1.4.0
bash scripts/publish_v1.4.0.sh --publish
```

The script will:

1. Reject a missing GitHub login, an existing `v1.4.0` tag/release, or a changed `main` branch (the archive is pinned to the reviewed PR #5 merge commit `a3b93d1`).
2. Clone `Kosztyk/orvibo_cloud` in a temporary directory and synchronize the production source tree, deleting obsolete beta-only files **without deleting the cloned `.git` metadata**.
3. Check the production manifest, run static checks, compile Python, install `pycryptodome==3.23.0` into a temporary virtualenv and run all regression tests. Verify that binary/TLS-sensitive files are unchanged from the baseline.
4. Commit and push the source to `main`.
5. Wait for the `Validate ORVIBO Cloud` GitHub Actions run to pass (packaging, security tests, HACS and Hassfest).
6. Create and push the annotated tag `v1.4.0`, causing `.github/workflows/release.yml` to validate and create the GitHub Release using `RELEASE_NOTES_1.4.0.md`.
7. Wait for that workflow, verify the published release and print its URL.

**Nothing is changed on GitHub merely by extracting the archive.** The `--publish` flag executes the external operations. If the run stops after a failed GitHub Actions check, do not tag manually; inspect and fix the workflow first.

## Manual publication alternative

If you prefer publishing by hand, ensure GitHub Actions **Validate ORVIBO Cloud** passed on `main`, then create/push an annotated tag `v1.4.0` targeting that validated commit. The tag-driven release workflow publishes the matching GitHub Release. Do not force-move release tags or publish from an unvalidated commit.

## Attribution and PR status

PR #5 by @matexdj **was merged** into `main` at commit `a3b93d1a521cad6eb8dce5c3df338e14d4f17ea7` before v1.4.0 was published. The release builds on the merged contribution and the maintainer-tested beta. Its publishing script pins that merge commit as the reviewed baseline and intentionally uses the validated v1.3.2 `binary.py`/`control.py` and TLS files instead of the PR's unverified stored-AC-OFF envelope.

### v1.4.0 release-package correction (13 November 2026)

The post-PR-#5 source package now synchronizes the root `README.md` and
`custom_components/orvibo_cloud/README.md` byte-for-byte. The publishing
script rejects a mismatched README before cloning or modifying GitHub.
Certificate-fixture generation in `tests/test_binary_security.py` uses an
OpenSSL configuration file for better macOS/LibreSSL portability while
retaining the original security assertions. These changes affect release
packaging and offline tests only; the runtime integration and IR encoder
are unchanged.

If a full-suite error persists, retain the traceback above `FAILED` as
well as the summary; the summary alone does not identify the exception.
