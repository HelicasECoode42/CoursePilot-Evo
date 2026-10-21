#!/usr/bin/env python3
"""Basic disclosure/link checks over Git-tracked content; not a security audit."""

import argparse
import os
from pathlib import Path
import posixpath
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SECRET = re.compile(
    r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{50,}|"
    r"sk-(?:proj-)?[A-Za-z0-9_-]{35,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)"
)
PRIVATE_EXTENSIONS = {".xls", ".xlsx", ".pdf", ".log"}
APPROVED_DERIVED_WORKBOOK = "data/curriculum/2024-computer-college-curricula.xlsx"


def git_bytes(*args: str) -> bytes:
    """Read Git metadata without forwarding Git output that could contain file data."""
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        raise SystemExit("self_check: unable to read Git index") from None


def tracked_paths() -> list[str]:
    return [os.fsdecode(name) for name in git_bytes("ls-files", "--cached", "-z").split(b"\0") if name]


def staged_paths() -> list[str]:
    listing = git_bytes("diff", "--cached", "--name-only", "--diff-filter=ACMRT", "-z")
    return [os.fsdecode(name) for name in listing.split(b"\0") if name]


def forbidden_path(relative: str) -> bool:
    path = Path(relative)
    parts = path.parts
    if parts[:2] in (("data", "raw"), ("data", "private")):
        return True
    # Allow only the reviewed A1 derivative; raw/private inputs remain blocked above.
    if relative.replace("\\", "/") == APPROVED_DERIVED_WORKBOOK:
        return False
    return path.suffix.lower() in PRIVATE_EXTENSIONS or (
        path.name.startswith(".env") and path.name != ".env.example"
    )


def staged_content(relative: str) -> bytes:
    # The index object is the only source in --staged mode. Never fall back to the worktree.
    return git_bytes("show", f":{relative}")


def worktree_content(relative: str) -> bytes | None:
    path = ROOT / relative
    try:
        if path.is_symlink():
            # Inspect the tracked link target text without following it outside the repository.
            return os.fsencode(os.readlink(path))
        return path.read_bytes()
    except FileNotFoundError:
        # A tracked file deleted from the worktree has no current content to inspect.
        return None
    except OSError:
        raise SystemExit(f"self_check: unable to read tracked path {relative}") from None


def local_markdown_links_exist(relative: str, text: str, staged: bool, index_paths: set[str]) -> list[str]:
    errors = []
    for destination in re.findall(r"\]\(([^)\n]+)\)", text):
        destination = destination.strip("<>").split("#", 1)[0]
        if not destination or "://" in destination or destination.startswith("mailto:"):
            continue
        if destination.startswith("/Users/"):
            errors.append(f"{relative}: public docs should use repository-relative links")
            continue
        target = posixpath.normpath(posixpath.join(posixpath.dirname(relative), destination))
        exists = target in index_paths if staged else (ROOT / target).exists()
        if not exists:
            errors.append(f"{relative}: missing local link {destination}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staged", action="store_true")
    args = parser.parse_args()

    index_paths = set(tracked_paths())
    paths = staged_paths() if args.staged else sorted(index_paths)
    errors: list[str] = []
    for relative in paths:
        # Apply filename/path gates before opening a worktree file or index blob.
        if forbidden_path(relative):
            errors.append(f"{relative}: private input/log file must not be committed")
            continue

        raw = staged_content(relative) if args.staged else worktree_content(relative)
        if raw is None:
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            continue

        if SECRET.search(text):
            errors.append(f"{relative}: possible credential/private key")
        if Path(relative).suffix.lower() == ".md":
            errors.extend(local_markdown_links_exist(relative, text, args.staged, index_paths))

    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"PASS: {len(paths)} Git-tracked files; basic disclosure and local Markdown link checks")
    print("Scope: text checks only; no guarantee against all secrets or runtime vulnerabilities")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
