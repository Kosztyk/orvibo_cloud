#!/usr/bin/env bash
# ORVIBO Cloud v1.4.1: fail-closed, pinned-base GitHub publisher.
# Usage: bash scripts/publish_v1.4.1.sh --check | --publish
# --check runs the complete local suite. Only --publish mutates GitHub.
set -euo pipefail

REPO='Kosztyk/orvibo_cloud'
BRANCH='main'
VERSION='1.4.1'
TAG="v${VERSION}"
EXPECTED_BASE='3a26fb1b30696e2d2ba41787a347c80f69a3f28c'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
if [[ -f "$SCRIPT_DIR/../custom_components/orvibo_cloud/manifest.json" ]]; then
  SOURCE="$(cd "$SCRIPT_DIR/.." && pwd -P)"
elif [[ -f "$SCRIPT_DIR/custom_components/orvibo_cloud/manifest.json" ]]; then
  SOURCE="$SCRIPT_DIR"
else
  echo 'ERROR: Use this script in the extracted full-source root or its scripts/ directory.' >&2
  exit 1
fi

fail() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '\n==> %s\n' "$*"; }
usage() {
  cat <<USAGE
ORVIBO Cloud v1.4.1 release publisher

  bash scripts/publish_v1.4.1.sh --check
      No GitHub changes; validates the complete release source and tests.

  bash scripts/publish_v1.4.1.sh --publish
      Requires gh auth. Publishes only if main still equals the reviewed
      v1.4.0 commit, local tests pass and new GitHub Actions CI passes.
      Pushes one commit to main, then annotated tag v1.4.1, waits for the
      tag workflow to create the Release and uploads both production ZIPs.

This script NEVER force-pushes, rewrites tags, or publishes in --check mode.
USAGE
}

case "${1:-}" in
  --check|--publish) [[ $# -eq 1 ]] || { usage; exit 2; }; MODE="$1" ;;
  *) usage; exit 2 ;;
esac

for tool in python3 git rsync; do
  command -v "$tool" >/dev/null 2>&1 || fail "Required tool missing: $tool"
done
python3 - <<'PY' || fail 'Python 3.13+ is required'
import sys
assert sys.version_info >= (3, 13)
PY

MANIFEST="$SOURCE/custom_components/orvibo_cloud/manifest.json"
[[ -f "$MANIFEST" ]] || fail 'Missing manifest'
[[ -f "$SOURCE/RELEASE_NOTES_${VERSION}.md" ]] || fail 'Missing current release notes'
[[ -f "$SOURCE/requirements-test.txt" ]] || fail 'Missing test dependencies'
[[ -f "$SOURCE/.github/workflows/validate.yml" ]] || fail 'Missing validation workflow'
[[ -f "$SOURCE/.github/workflows/release.yml" ]] || fail 'Missing tag release workflow'
[[ -f "$SOURCE/THIRD_PARTY_NOTICES.md" ]] || fail 'Missing license attribution'
[[ -f "$SOURCE/LICENSES/LGPL-2.1.txt" ]] || fail 'Missing Daikin LGPL text'
cmp -s "$SOURCE/README.md" "$SOURCE/custom_components/orvibo_cloud/README.md" || fail 'Root and bundled README differ'
cmp -s "$SOURCE/THIRD_PARTY_NOTICES.md" "$SOURCE/custom_components/orvibo_cloud/THIRD_PARTY_NOTICES.md" || fail 'License notices differ'

python3 - "$SOURCE" "$VERSION" <<'PY' || fail 'Invalid source/version/whitespace'
import json,sys
from pathlib import Path
root=Path(sys.argv[1]); version=sys.argv[2]
m=json.loads((root/'custom_components/orvibo_cloud/manifest.json').read_text())
assert m['version']==version, f"Expected {version}, got {m['version']}"
assert m['domain']=='orvibo_cloud'
for p in root.rglob('*'):
    if not p.is_file() or any(part in {'.git','.venv','__pycache__'} for part in p.parts): continue
    if p.suffix not in {'.md','.py','.sh','.yml','.yaml','.json','.toml','.txt'}: continue
    for i,line in enumerate(p.read_text(encoding='utf-8').splitlines(),1):
        if line!=line.rstrip(' \t'):
            raise RuntimeError(f"Trailing whitespace: {p.relative_to(root)}:{i}")
PY

TMP_RELEASE="$(mktemp -d)"
trap 'rm -rf "$TMP_RELEASE"' EXIT

info 'Copying source to an isolated validation directory'
mkdir -p "$TMP_RELEASE/checkout"
rsync -a --delete --exclude='.git' --exclude='.venv' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='.DS_Store' "$SOURCE/" "$TMP_RELEASE/checkout/"

info 'Installing all release test dependencies into a temporary Python environment'
python3 -m venv "$TMP_RELEASE/venv"
PYTHON="$TMP_RELEASE/venv/bin/python"
"$PYTHON" -m pip install --disable-pip-version-check -r "$TMP_RELEASE/checkout/requirements-test.txt"
(
  cd "$TMP_RELEASE/checkout"
  "$PYTHON" tools/check_repository.py
  "$PYTHON" -m unittest discover -s tests -v
  "$PYTHON" -m compileall -q custom_components
  "$PYTHON" tools/build_release_archives.py --version "$VERSION" --output "$TMP_RELEASE/local_assets"
)

if [[ "$MODE" == '--check' ]]; then
  info 'PASS: all local checks completed. No GitHub commands were executed.'
  exit 0
fi

for tool in gh; do
  command -v "$tool" >/dev/null 2>&1 || fail "Required publishing tool missing: $tool (install GitHub CLI and run gh auth login)"
done
gh auth status --hostname github.com >/dev/null || fail 'Run gh auth login first'
[[ "$(gh api "repos/${REPO}" --jq '.default_branch')" == "$BRANCH" ]] || fail 'Unexpected default branch'
if gh release view "$TAG" --repo "$REPO" >/dev/null 2>&1; then
  fail "Release ${TAG} already exists"
fi
[[ -z "$(git ls-remote --tags "https://github.com/${REPO}.git" "refs/tags/$TAG")" ]] || fail "Tag ${TAG} already exists"

info 'Fetching a fresh, clean main checkout from GitHub'
gh repo clone "$REPO" "$TMP_RELEASE/repo" -- --branch "$BRANCH" --depth 1
CHECKOUT="$TMP_RELEASE/repo"
ACTUAL_BASE="$(git -C "$CHECKOUT" rev-parse HEAD)"
[[ "$ACTUAL_BASE" == "$EXPECTED_BASE" ]] || fail "main HEAD differs from reviewed v1.4.0: expected $EXPECTED_BASE, found $ACTUAL_BASE. Refusing to overwrite."

info 'Verifying production cloud transport and TLS assets against v1.4.0'
for path in \
  custom_components/orvibo_cloud/binary.py \
  custom_components/orvibo_cloud/control.py \
  custom_components/orvibo_cloud/orvibo_client_cert.pem \
  custom_components/orvibo_cloud/orvibo_client_key.pem \
  custom_components/orvibo_cloud/orvibo_server_ca.pem \
  custom_components/orvibo_cloud/midea_48.py \
  custom_components/orvibo_cloud/climate.py \
  custom_components/orvibo_cloud/ac_backend.py
do
  git -C "$CHECKOUT" show "HEAD:$path" | cmp - "$SOURCE/$path" >/dev/null || fail "Sensitive production file unexpectedly changed: $path"
done

info 'Synchronizing production source onto the pinned v1.4.0 checkout'
rsync -a --delete --exclude='/.git/' --exclude='.venv' --exclude='__pycache__' \
  --exclude='*.pyc' --exclude='.DS_Store' "$SOURCE/" "$CHECKOUT/"
git -C "$CHECKOUT" add -A
git -C "$CHECKOUT" diff --cached --check
if git -C "$CHECKOUT" diff --cached --quiet; then
  fail 'No changes to publish'
fi
info 'Showing the exact planned production change list'
git -C "$CHECKOUT" diff --cached --stat

# Refuse an unexpected concurrent main change between clone and push.
REMOTE_HEAD="$(git ls-remote "https://github.com/${REPO}.git" "refs/heads/$BRANCH" | cut -f1)"
[[ "$REMOTE_HEAD" == "$EXPECTED_BASE" ]] || fail "Remote main changed before publication ($REMOTE_HEAD). No push performed."

git -C "$CHECKOUT" -c user.name="$(gh api user --jq '.login')" -c user.email="$(gh api user --jq '.id')+$(gh api user --jq '.login')@users.noreply.github.com" \
  commit -m "Release ORVIBO Cloud $TAG — LS175 controls, BAXI swing and provenance"
COMMIT="$(git -C "$CHECKOUT" rev-parse HEAD)"

info "Pushing validated source commit $COMMIT to main"
git -C "$CHECKOUT" push origin "HEAD:refs/heads/$BRANCH"

wait_for_workflow() {
  local workflow="$1" run_id='' i
  info "Waiting for ${workflow} GitHub Actions on commit ${COMMIT}"
  for ((i=0;i<60;i++)); do
    run_id="$(gh run list --repo "$REPO" --workflow "$workflow" --event push --commit "$COMMIT" --limit 20 --json databaseId --jq '.[0].databaseId // empty')"
    [[ -n "$run_id" ]] && break
    sleep 6
  done
  [[ -n "$run_id" ]] || fail "GitHub Actions workflow ${workflow} did not appear. Code may already be pushed; inspect repository Actions before proceeding."
  gh run watch "$run_id" --repo "$REPO" --exit-status || fail "${workflow} failed. Do not tag/publish until fixed. Source commit may already be on main."
}

# Ensure HACS, Hassfest and unit/security checks passed on the published commit.
wait_for_workflow 'validate.yml'

info "Tagging and publishing ${TAG} after successful main CI"
git -C "$CHECKOUT" tag -a "$TAG" -m "ORVIBO Cloud ${TAG} — stable IR device controls"
git -C "$CHECKOUT" push origin "refs/tags/$TAG"
wait_for_workflow 'release.yml'

info 'Attaching both reviewed production archives to the GitHub Release'
# Reuse locally validated ZIPs; avoid assembling a different code snapshot.
gh release upload "$TAG" --repo "$REPO" \
  "$TMP_RELEASE/local_assets/orvibo_cloud_v${VERSION}_ha_install.zip" \
  "$TMP_RELEASE/local_assets/orvibo_cloud_v${VERSION}_full_source.zip"
URL="$(gh release view "$TAG" --repo "$REPO" --json url --jq '.url')"
[[ "$URL" == "https://github.com/${REPO}/releases/tag/${TAG}" ]] || fail "Unexpected release URL: $URL"
info "SUCCESS: ${URL}"
