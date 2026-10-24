# Publishing ORVIBO Cloud in HACS

1. Merge the HACS readiness PR only after the HACS, Hassfest and packaging
   checks pass on the PR branch.
2. Recheck GitHub Actions after the merge. The narrowly scoped release workflow
   publishes `v1.3.2` only after the `Validate ORVIBO Cloud` workflow succeeds
   for a `push` on the current `main` HEAD. If it fails, publish that tag as
   a full GitHub Release manually, using `RELEASE_NOTES_1.3.2.md`.
3. Confirm that the release was created **after successful validations**.
4. Test in HACS > Custom repositories as category **Integration**:

   https://github.com/Kosztyk/orvibo_cloud

5. In your personal fork of `hacs/default`, create a separate branch from
   `master` and add `"Kosztyk/orvibo_cloud"` to the alphabetically sorted
   `integration` file.
6. Open a PR against `hacs/default:master` and complete **all** checkboxes in
   the default HACS PR template. Include links to the final release and
   successful HACS and Hassfest GitHub Actions jobs.

Official requirements: https://www.hacs.xyz/docs/publish/include/

HACS maintainers will review the request. Do not request reviews, post
unnecessary comments or open duplicate submissions.

## Current submission

After validation on the updated main branch, use the existing HACS PR #12441. Do not open a duplicate. Update its release and passing validation URLs; mark the existing PR ready for review after the five changes are addressed.
