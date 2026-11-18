"""Withdraw credential-bearing releases and rewrite owned Git refs once."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

REPOSITORY = "Kosztyk/orvibo_cloud"
CREDENTIAL_NAMES = {"orvibo_client_cert.pem", "orvibo_client_key.pem"}
EXPECTED_REFS = {
    "refs/heads/hacs-review-v1.3.2-clean": "6fe93924cc0bbf442f0205d312932dd727228f40",
    "refs/tags/V1.1.0": "1ccd259bd3e870e93da454789d5ac994b0f3feca",
    "refs/tags/V1.3.0": "b6d835469678424a1cf196e5f2022bc9cf3723d1",
    "refs/tags/v1.3.1": "6fe93924cc0bbf442f0205d312932dd727228f40",
    "refs/tags/v1.3.2": "3d70f77eeecfc955a5e2ea19ca7693b21156d913",
    "refs/tags/v1.4.0": "6508380d7a96d2dba04819c3de473bc07db0094d",
    "refs/tags/v1.4.1": "7ace20b8e1a828e003d82e3445898ffec4c1240f",
    "refs/tags/v1.4.2": "d67587b6717789805f89367e1237b7748711922f",
}
EXPECTED_RELEASES = {
    "v1.4.2": 447465525, "v1.4.1": 445175686, "v1.4.0": 444426985,
    "v1.3.2": 423024423, "v1.3.1": 420783376,
    "V1.3.0": 417189477, "V1.1.0": 414269210,
}
PRIVATE_KEY = re.compile(
    rb"-----BEGIN (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----\r?\n"
    rb"[A-Za-z0-9+/=\r\n]+-----END (?:RSA |EC |ENCRYPTED )?PRIVATE KEY-----"
)


def run(*args: str, cwd: Path | None = None) -> bytes:
    return subprocess.check_output(args, cwd=cwd)


def api(path: str, method: str = "GET"):
    response = run("gh", "api", "--method", method, f"repos/{REPOSITORY}/{path}")
    return json.loads(response) if response else None


def refs(repo: Path) -> dict[str, str]:
    rows = run("git", "for-each-ref", "--format=%(refname) %(objectname)",
               "refs/heads", "refs/tags", cwd=repo).decode().splitlines()
    return dict(row.split() for row in rows)


def tree(repo: Path, commit: str) -> dict[str, str]:
    result = {}
    for entry in run("git", "ls-tree", "-rz", commit, cwd=repo).split(b"\0"):
        if entry:
            metadata, path = entry.split(b"\t", 1)
            result[path.decode()] = metadata.decode()
    return result


def audit(repo: Path) -> None:
    for entry in run("git", "rev-list", "--objects", "--all", cwd=repo).decode().splitlines():
        oid, _, path = entry.partition(" ")
        if Path(path).name in CREDENTIAL_NAMES:
            raise RuntimeError(f"Credential filename remains at {path}")
        if run("git", "cat-file", "-t", oid, cwd=repo).strip() == b"blob":
            data = run("git", "cat-file", "blob", oid, cwd=repo)
            if PRIVATE_KEY.search(data):
                raise RuntimeError(f"Private-key material remains at {path}")
    for oid in ("866f2fd4669de8b1720061d40dc923e07725273e",
                "a95effd1e4314082e05a58e872e19649fedaf995"):
        check = subprocess.run(["git", "cat-file", "-e", oid], cwd=repo,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check.returncode == 0:
            raise RuntimeError("Original credential object remains in the local object database")


def main() -> None:
    if (os.environ.get("GITHUB_REPOSITORY") != REPOSITORY
            or os.environ.get("GITHUB_EVENT_NAME") != "workflow_dispatch"):
        raise RuntimeError("This one-time cleanup requires a manual run in the owned repository")
    expected = {**EXPECTED_REFS, "refs/heads/main": os.environ["GITHUB_SHA"]}
    publisher = api("actions/workflows/release.yml")
    if publisher["state"] != "disabled_manually":
        raise RuntimeError("Pause the release-publishing workflow before rewriting refs")
    releases = api("releases?per_page=100")
    if {item["tag_name"]: item["id"] for item in releases} != EXPECTED_RELEASES:
        raise RuntimeError("Release inventory changed and requires review")
    if any(item.get("immutable") for item in releases):
        raise RuntimeError("An immutable release requires separate withdrawal handling")

    run("gh", "auth", "setup-git")
    with tempfile.TemporaryDirectory(prefix="orvibo-withdrawal-") as directory:
        root = Path(directory)
        mirror = root / "clean.git"
        url = f"https://github.com/{REPOSITORY}.git"
        subprocess.run(["git", "clone", "--mirror", url, str(mirror)], check=True)
        original_refs = refs(mirror)
        if original_refs != expected:
            raise RuntimeError("Branch or tag inventory changed and requires review")
        originals = {
            oid: tree(mirror, oid)
            for oid in run("git", "rev-list", "--all", cwd=mirror).decode().splitlines()
        }
        subprocess.run([
            "git", "filter-repo", "--sensitive-data-removal", "--invert-paths",
            "--use-base-name", "--path", "orvibo_client_cert.pem",
            "--path", "orvibo_client_key.pem",
        ], cwd=mirror, check=True)
        mapping = dict(line.split() for line in
                       (mirror / "filter-repo/commit-map").read_text().splitlines()[1:])
        cleaned_trees = {
            oid: tree(mirror, oid)
            for oid in run("git", "rev-list", "--all", cwd=mirror).decode().splitlines()
        }
        for old, original in originals.items():
            wanted = {path: value for path, value in original.items()
                      if Path(path).name not in CREDENTIAL_NAMES}
            new = mapping[old]
            if new == "0" * 40:
                if wanted not in cleaned_trees.values():
                    raise RuntimeError("A removed commit contained unrelated changes")
            elif cleaned_trees[new] != wanted:
                raise RuntimeError("The rewrite changed unrelated file contents")
        audit(mirror)

        # Recheck every mutable ref immediately before the irreversible writes.
        live = dict(line.split()[::-1] for line in run(
            "git", "ls-remote", "--refs", "--heads", "--tags", url
        ).decode().splitlines())
        if live != original_refs:
            raise RuntimeError("A remote branch or tag changed during cleanup")
        for release in releases:
            api(f"releases/{release['id']}", "DELETE")
            print(f"Withdrew release {release['tag_name']} and its attached assets")
        cleaned_refs = refs(mirror)
        leases = [f"--force-with-lease={ref}:{oid}" for ref, oid in original_refs.items()]
        changes = [
            f"{ref}:{ref}" if ref.startswith("refs/heads/") else f":{ref}"
            for ref in original_refs
        ]
        subprocess.run([
            "git", "-c", "remote.origin.mirror=false", "push", "--atomic",
            *leases, "origin", *changes,
        ], cwd=mirror, check=True)

        check = root / "verification.git"
        subprocess.run(["git", "clone", "--mirror", url, str(check)], check=True)
        maintained = refs(check)
        expected_heads = {ref: oid for ref, oid in cleaned_refs.items()
                          if ref.startswith("refs/heads/")}
        if maintained != expected_heads or api("releases?per_page=100"):
            raise RuntimeError("Public branch, tag or release verification failed")
        # GitHub owns refs/pull. Exclude those read-only refs from the owned-ref audit.
        for entry in run("git", "for-each-ref", "--format=%(refname)",
                         "refs/pull", cwd=check).decode().splitlines():
            subprocess.run(["git", "update-ref", "-d", entry], cwd=check, check=True)
        subprocess.run(["git", "reflog", "expire", "--expire=now", "--all"], cwd=check, check=True)
        subprocess.run(["git", "gc", "--prune=now"], cwd=check, check=True)
        audit(check)
        changed = (mirror / "filter-repo/changed-refs").read_text().splitlines()
        pull_refs = [ref for ref in changed if ref.startswith("refs/pull/")]
        summary = (
            "## Credential withdrawal completed for owned refs\n\n"
            f"Verified {len(originals)} original commit trees and preserved all unrelated file contents.\n\n"
            f"Rewrote {len(expected_heads)} maintained branches. Deleted {len(EXPECTED_RELEASES)} releases "
            "and their attached assets, and deleted seven affected tags.\n\n"
            "GitHub Support and fork owners still need to remove their historical references.\n\n"
            "Affected read-only pull refs\n\n" + "\n".join(f"- `{ref}`" for ref in pull_refs)
            + "\n\nCoordination is tracked in issue #6.\n"
        )
        Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(summary)
        print(summary)


if __name__ == "__main__":
    main()
