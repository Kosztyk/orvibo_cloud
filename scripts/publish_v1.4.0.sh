#!/usr/bin/env bash
# Publish ORVIBO Cloud v1.4.0 after the merge of PR #5.
# Pin expected main HEAD, verify trusted v1.3.2 TLS/transport baseline.
# No repository mutation without --publish.
set -euo pipefail

REPO='Kosztyk/orvibo_cloud'
BRANCH='main'
VERSION='1.4.0'
TAG="v${VERSION}"
EXPECTED_BASE='15d40323dba7e8d87aee3621dee5e9714bdbead4'
TRUSTED_V132_BASE='3d70f77eeecfc955a5e2ea19ca7693b21156d913'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# Accept both the bundled scripts/ location and a separately downloaded copy
# placed at the root of the extracted full-source archive.
if [[ -f "$SCRIPT_DIR/../custom_components/orvibo_cloud/manifest.json" ]]; then
  SOURCE="$(cd "$SCRIPT_DIR/.." && pwd -P)"
elif [[ -f "$SCRIPT_DIR/custom_components/orvibo_cloud/manifest.json" ]]; then
  SOURCE="$SCRIPT_DIR"
else
  echo "ERROR: Put this script in the extracted full-source root or its scripts/ directory." >&2
  exit 1
fi

usage() {
  cat <<USAGE
Publish ORVIBO Cloud ${TAG} to https://github.com/${REPO}

Run from the extracted full-source release ZIP:
  bash scripts/publish_v1.4.0.sh --publish

This script clones a fresh repo at merged PR #5, verifies its baseline,
validates the release source,
commits and pushes to main, waits for CI, then tags and waits for GitHub
Actions to create the official release. Nothing is pushed without --publish.
USAGE
}

if [[ "${1:-}" != '--publish' || "$#" -ne 1 ]]; then
  usage
  exit 2
fi

fail() { echo "ERROR: $*" >&2; exit 1; }
info() { echo; echo "==> $*"; }
for cmd in git gh rsync python3; do
  command -v "$cmd" >/dev/null 2>&1 || fail "Missing required command: $cmd"
done
python3 - <<'PY_VERSION' || fail "Python 3.13 or newer is required to publish"
import sys
assert sys.version_info >= (3, 13)
PY_VERSION
[[ -f "$SOURCE/custom_components/orvibo_cloud/manifest.json" ]] || fail 'Full source not found. Run from inside the extracted production source archive.'
[[ -f "$SOURCE/RELEASE_NOTES_${VERSION}.md" ]] || fail 'Release notes are missing.'
[[ -f "$SOURCE/.github/workflows/validate.yml" ]] || fail 'Validation workflow missing.'
[[ -f "$SOURCE/.github/workflows/release.yml" ]] || fail 'Release workflow missing.'
[[ -s "$SOURCE/requirements-test.txt" ]] || fail 'Test dependency manifest missing.'
[[ -f "$SOURCE/custom_components/orvibo_cloud/README.md" ]] || fail 'Bundled README is missing.'
cmp -s "$SOURCE/README.md" "$SOURCE/custom_components/orvibo_cloud/README.md" || \
  fail 'Root README and bundled integration README differ. Do not publish mismatched documentation.'

# Reject source whitespace mistakes before cloning, dependency installation or CI.
python3 - "$SOURCE" <<'PY_TRAILING' || fail 'Release source contains trailing whitespace. Correct it before publishing.'
from pathlib import Path
import sys

root = Path(sys.argv[1])
errors = []
for path in sorted(root.rglob('*')):
    if not path.is_file() or any(part in {'__pycache__', '.git', '.venv'} for part in path.parts):
        continue
    if path.suffix not in {'.md', '.py', '.sh', '.yml', '.yaml', '.json', '.toml', '.txt'}:
        continue
    for number, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
        if line != line.rstrip(' \t'):
            errors.append(f'{path.relative_to(root)}:{number}')
if errors:
    print('Trailing whitespace found in release source:', file=sys.stderr)
    for entry in errors:
        print(f'  {entry}', file=sys.stderr)
    sys.exit(1)
PY_TRAILING

gh auth status --hostname github.com >/dev/null || fail 'Log in with: gh auth login'
[[ "$(gh api "repos/${REPO}" --jq '.default_branch')" == "$BRANCH" ]] || fail 'Default branch is no longer main.'
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  fail "Release $TAG already exists. Refusing to publish twice."
fi
if [[ -n "$(git ls-remote --tags "https://github.com/${REPO}.git" "refs/tags/$TAG")" ]]; then
  fail "Tag $TAG already exists. Refusing to overwrite it."
fi

TMPDIR_RELEASE="$(mktemp -d)"
trap 'rm -rf "$TMPDIR_RELEASE"' EXIT
CHECKOUT="$TMPDIR_RELEASE/repo"

info "Cloning $REPO"
gh repo clone "$REPO" "$CHECKOUT" -- --depth 1 --branch "$BRANCH"
ACTUAL_BASE="$(git -C "$CHECKOUT" rev-parse HEAD)"
[[ "$ACTUAL_BASE" == "$EXPECTED_BASE" ]] || fail "main changed since package preparation ($ACTUAL_BASE; expected $EXPECTED_BASE). Regenerate/review before overwriting."

# PR #5 has already been merged at EXPECTED_BASE. Its original experimental
# binary.py/control.py changes were intentionally NOT kept in v1.4.0 after
# maintainer hardware tests. Verify the exact pre-PR trusted source, rather
# than comparing those two files to the merged HEAD (which would fail).
info 'Verifying PR #5 ancestry and the pinned v1.3.2 security baseline'
git -C "$CHECKOUT" fetch --quiet --deepen=5 origin "$BRANCH"
git -C "$CHECKOUT" cat-file -e "${TRUSTED_V132_BASE}^{commit}" || fail 'The reviewed v1.3.2 commit is missing.'
git -C "$CHECKOUT" merge-base --is-ancestor "$TRUSTED_V132_BASE" "$EXPECTED_BASE" || fail 'Unexpected branch history: v1.3.2 is not an ancestor.'

info 'Synchronizing the reviewed production source onto the merged PR #5 commit'
rsync -a --delete \
  --exclude='/.git/' \
  --exclude='/.venv/' \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='.DS_Store' \
  "$SOURCE/" "$CHECKOUT/"

# Production binary/control and TLS assets must be byte-for-byte identical
# to the published v1.3.2 code. PR #5 introduced an experimental stored-AC-OFF
# envelope in binary.py/control.py that was NOT part of the verified v1.4.0
# production beta. Reverting only that unverified path is intentional.
for path in \
  custom_components/orvibo_cloud/binary.py \
  custom_components/orvibo_cloud/control.py \
  custom_components/orvibo_cloud/orvibo_client_cert.pem \
  custom_components/orvibo_cloud/orvibo_client_key.pem \
  custom_components/orvibo_cloud/orvibo_server_ca.pem
do
  git -C "$CHECKOUT" cat-file -e "${TRUSTED_V132_BASE}:$path" || fail "v1.3.2 source file missing: $path"
  git -C "$CHECKOUT" show "${TRUSTED_V132_BASE}:$path" | cmp - "$CHECKOUT/$path" >/dev/null || fail "Sensitive source unexpectedly changed from reviewed v1.3.2: $path"
  if ! git -C "$CHECKOUT" show "HEAD:$path" | cmp - "$CHECKOUT/$path" >/dev/null; then
    echo "Reviewed intentional PR #5 rollback to known-good v1.3.2: $path"
  fi
done

info 'Validating manifest and full test suite'
MANIFEST_VERSION="$(python3 - "$CHECKOUT/custom_components/orvibo_cloud/manifest.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))['version'])
PY
)"
[[ "$MANIFEST_VERSION" == "$VERSION" ]] || fail "Manifest version mismatch: $MANIFEST_VERSION"
python3 -m venv "$TMPDIR_RELEASE/venv"
PYTHON="$TMPDIR_RELEASE/venv/bin/python"
"$PYTHON" -m pip install --disable-pip-version-check --quiet -r "$CHECKOUT/requirements-test.txt"
(
  cd "$CHECKOUT"
  "$PYTHON" tools/check_repository.py
  "$PYTHON" -m unittest discover -s tests -v
  "$PYTHON" -m compileall -q custom_components
)

info 'Preparing source commit'
git -C "$CHECKOUT" add -A
git -C "$CHECKOUT" diff --cached --check
if git -C "$CHECKOUT" diff --cached --quiet; then
  fail 'No repository changes to publish.'
fi
git -C "$CHECKOUT" diff --cached --stat
git -C "$CHECKOUT" commit -m "Release ORVIBO Cloud $TAG with native IR climate controls"
COMMIT="$(git -C "$CHECKOUT" rev-parse HEAD)"

info "Pushing $BRANCH at $COMMIT"
git -C "$CHECKOUT" push origin "HEAD:refs/heads/${BRANCH}"

wait_for_workflow() {
  local workflow="$1" event="$2" id='' i
  info "Waiting for GitHub Actions $workflow ($event) on $COMMIT"
  for ((i=0;i<50;i++)); do
    id="$(gh run list --repo "$REPO" --workflow "$workflow" --event "$event" --commit "$COMMIT" --limit 10 --json databaseId --jq '.[0].databaseId // empty')"
    [[ -n "$id" ]] && break
    sleep 6
  done
  [[ -n "$id" ]] || fail "No $workflow workflow run appeared. Inspect https://github.com/$REPO/actions (code already pushed)."
  gh run watch "$id" --repo "$REPO" --exit-status || fail "$workflow CI failed. Do not tag or release this revision."
}

# Full validation: packaging, TLS, HACS and Hassfest all must pass on main.
wait_for_workflow 'validate.yml' 'push'

info "Creating and pushing annotated production tag $TAG"
git -C "$CHECKOUT" tag -a "$TAG" -m "ORVIBO Cloud $TAG — native IR climate controls"
git -C "$CHECKOUT" push origin "refs/tags/$TAG"

# Tag workflow performs its own packaging/security checks and creates release.
wait_for_workflow 'release.yml' 'push'
RELEASE_URL="$(gh release view "$TAG" --repo "$REPO" --json url --jq '.url')"
[[ "$RELEASE_URL" == "https://github.com/${REPO}/releases/tag/${TAG}" ]] || fail "Unexpected release URL: $RELEASE_URL"
info "SUCCESS: $RELEASE_URL"
