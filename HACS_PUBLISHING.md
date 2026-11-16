# Publishing ORVIBO Cloud

ORVIBO Cloud is in the HACS default catalog. HACS downloads the integration from the GitHub release tag. The repository keeps the integration and its brand assets under `custom_components/orvibo_cloud`. [HACS catalog entry](https://github.com/hacs/default/pull/12441)

## Validate the release

Use the Python version configured in GitHub Actions. The current workflows use Python 3.13.

```bash
python3.13 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python tools/check_repository.py
python -m unittest discover -s tests -v
python -m compileall -q custom_components
python tools/build_release_archives.py --version 1.4.2 --output /tmp/orvibo-cloud-release
```

Check that the manifest version, version-specific release notes and archive names agree. Package validation compares the repository README with the copy included in HACS installations. The archive builder writes an integration-only ZIP for manual installation and a full source ZIP. The GitHub validation workflow also runs HACS and Hassfest.

## Publish the validated commit

1. Push the release commit to `main` and verify the validation checks on that commit.
2. Create the stable tag `v1.4.2` on the validated commit and push the tag. The existing release workflow checks the version, runs the tests and publishes the GitHub release using `RELEASE_NOTES_1.4.2.md`.
3. Confirm the published release points to that commit. Attach the manual installation and full source ZIPs when distributing those builds. The release's GitHub source archives also contain the complete integration.

```bash
git tag -a v1.4.2 -m "ORVIBO Cloud v1.4.2"
git push origin refs/tags/v1.4.2
gh release view v1.4.2
```

Users can update through HACS and restart Home Assistant. [GitHub Actions](https://github.com/Kosztyk/orvibo_cloud/actions) · [GitHub releases](https://github.com/Kosztyk/orvibo_cloud/releases)

## Update checklist

- Update the manifest, both README copies, changelog and release notes.
- Keep the device support table and hardware validation notes aligned with evidence from the tested build.
- Include the Daikin encoder's LGPL attribution and license in all archives. [Third-party notices](THIRD_PARTY_NOTICES.md) · [Validation](VALIDATION.md)
