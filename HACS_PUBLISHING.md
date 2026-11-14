# Publishing ORVIBO Cloud v1.4.1

The repository is already in the HACS default catalog. Publishing a new GitHub release does **not** require another `hacs/default` pull request. The stable version is **v1.4.1**, based on the previously published v1.4.0 commit `3a26fb1b30696e2d2ba41787a347c80f69a3f28c`.

## Requirements

- Git, `rsync`, **Python 3.13+** with `venv` and `pip`, and [GitHub CLI (`gh`)](https://cli.github.com/).
- An authenticated GitHub account with permission to push `Kosztyk/orvibo_cloud` and create tags/releases. Authenticate using `gh auth login` and confirm `gh auth status`.
- Network access to install the packages listed in `requirements-test.txt` (`aiohttp`, `pycryptodome`) and to access GitHub.
- Working GitHub Actions permissions for HACS, Hassfest and release publication.

## Step 1: extract the full source

```bash
unzip orvibo_cloud_v1.4.1_full_source.zip
cd orvibo_cloud_v1.4.1
```

## Step 2: run the **non-publishing** validation

```bash
bash scripts/publish_v1.4.1.sh --check
```

This performs all static/HACS package checks, installs test dependencies in a temporary Python virtual environment, runs the complete unittest/security suite, compiles Python code and builds release archives. It **never** pushes or tags anything, and it does not alter your Home Assistant installation.

## Step 3: publish only after you review the package

```bash
bash scripts/publish_v1.4.1.sh --publish
```

The publisher fails closed if `main` has changed from the exact reviewed v1.4.0 commit, if the v1.4.1 tag or release exists, if the release manifest/docs are inconsistent, if the TLS/transport/Vivax baseline files changed, or if local tests fail. It:

1. Validates the full production source including the TLS test module (the test dependency is installed beforehand).
2. Clones `Kosztyk/orvibo_cloud` into a temporary directory; refuses any unexpected main-branch change and displays the staged diff summary.
3. Commits and **pushes to `main`** using a regular non-force push.
4. Waits for the GitHub `Validate ORVIBO Cloud` workflow (unit/security, HACS and Hassfest). If CI fails, **stops without tagging**; the source commit may already have been pushed, so fix the failure rather than rerunning blindly.
5. Creates and pushes an annotated `v1.4.1` tag on the validated commit.
6. Waits for `.github/workflows/release.yml` to create the **non-prerelease GitHub Release** using `RELEASE_NOTES_1.4.1.md`.
7. Uploads `orvibo_cloud_v1.4.1_ha_install.zip` and `orvibo_cloud_v1.4.1_full_source.zip` as release assets and displays the release URL.

The tag-workflow may finish before the asset upload, in which case the release initially contains GitHub's automatic source archives; the publisher then attaches the two convenient ZIP files. The configured `hacs.json` uses normal source-tag installation, not `zip_release: true`.

**The archive itself does not publish anything.** Merely extracting it or running `--check` cannot change GitHub. Only `--publish` initiates publication.

## Important release limitations

- Blaupunkt Power is an **optimistic switch** using a relative IR toggle, not actual feedback; external remote actions can desynchronize it.
- BAXI Horizontal was verified physically in Carlos's experimental fork and has distinct offline signal vectors, but its exact v1.4.1 runtime should be retested physically when possible.
- Cloud-reported hub online status can remain stale for a while after unplugging, even while the ORVIBO cloud connection sensor remains On. The maintainer verified recovery without restarting HA on 2026-11-14.
- `daikin_arc433.py` carries **LGPL-2.1-only** source attribution, which is separate from the MIT license for other files.

See `RELEASE_NOTES_1.4.1.md`, `VALIDATION.md`, `THIRD_PARTY_NOTICES.md` and `PROVENANCE_AUDIT.md`.
