#!/usr/bin/env python3
"""Regression checks for self_check against isolated temporary Git repositories."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).with_name("self_check.py")
CANARY = "ghp_" + "A" * 40
PRIVATE_CONTENT = "SYNTHETIC-PRIVATE-CONTENT-9f8a2d"


class SelfCheckRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="coursepilot-self-check-")
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        shutil.copy2(SOURCE, self.root / "scripts" / "self_check.py")
        self.git("init", "-q")
        self.git("config", "user.name", "Self Check Test")
        self.git("config", "user.email", "self-check@example.invalid")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args], cwd=self.root, check=True, capture_output=True, text=True
        )

    def check(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.pop("GIT_DIR", None)
        env.pop("GIT_WORK_TREE", None)
        return subprocess.run(
            [sys.executable, "scripts/self_check.py", *args],
            cwd=self.root,
            capture_output=True,
            text=True,
            env=env,
        )

    def commit_all(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", "baseline")

    def test_default_scans_force_tracked_private_path_without_printing_contents(self) -> None:
        private = self.root / "data" / "private" / "synthetic-record.json"
        private.parent.mkdir(parents=True)
        private.write_text('{"sentinel":"' + PRIVATE_CONTENT + '"}', encoding="utf-8")
        self.git("add", "-f", "data/private/synthetic-record.json")

        result = self.check()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("data/private/synthetic-record.json", result.stderr)
        self.assertNotIn(PRIVATE_CONTENT, result.stdout + result.stderr)

    def test_default_scans_tracked_regular_text(self) -> None:
        (self.root / "notes.txt").write_text("ordinary tracked text", encoding="utf-8")
        self.git("add", "notes.txt")
        self.commit_all()
        (self.root / "notes.txt").write_text(CANARY, encoding="utf-8")

        result = self.check()

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("notes.txt: possible credential/private key", result.stderr)
        self.assertNotIn(CANARY, result.stdout + result.stderr)

    def test_ignored_untracked_private_input_is_not_scanned(self) -> None:
        (self.root / ".gitignore").write_text("local-input.txt\n", encoding="utf-8")
        self.git("add", ".gitignore")
        self.commit_all()
        (self.root / "local-input.txt").write_text(CANARY, encoding="utf-8")

        result = self.check()

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("local-input.txt", result.stdout + result.stderr)

    def test_staged_mode_reads_index_content_not_worktree_content(self) -> None:
        text = self.root / "tracked.txt"
        text.write_text("baseline", encoding="utf-8")
        self.git("add", "tracked.txt")
        self.commit_all()

        text.write_text("staged safe", encoding="utf-8")
        self.git("add", "tracked.txt")
        text.write_text(CANARY, encoding="utf-8")
        result = self.check("--staged")
        self.assertEqual(result.returncode, 0, result.stderr)

        text.write_text(CANARY, encoding="utf-8")
        self.git("add", "tracked.txt")
        text.write_text("worktree safe", encoding="utf-8")
        result = self.check("--staged")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tracked.txt: possible credential/private key", result.stderr)
        self.assertNotIn(CANARY, result.stdout + result.stderr)

    def test_staged_deletion_is_not_reported_as_a_private_file(self) -> None:
        private = self.root / "data" / "private" / "record.json"
        private.parent.mkdir(parents=True)
        private.write_text("synthetic", encoding="utf-8")
        self.git("add", "-f", "data/private/record.json")
        self.commit_all()
        self.git("rm", "--cached", "--", "data/private/record.json")

        result = self.check("--staged")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("data/private/record.json", result.stdout + result.stderr)

    def test_staged_symlink_to_regular_file_type_change_scans_index_blob(self) -> None:
        tracked = self.root / "tracked.txt"
        try:
            os.symlink("safe-target.txt", tracked)
        except (OSError, NotImplementedError) as error:
            self.skipTest(f"symlinks are unavailable: {error}")
        self.git("add", "tracked.txt")
        self.commit_all()

        tracked.unlink()
        tracked.write_text(CANARY, encoding="utf-8")
        self.git("add", "tracked.txt")
        staged_status = self.git("diff", "--cached", "--name-status").stdout
        self.assertIn("T\ttracked.txt", staged_status)

        # A different safe worktree value ensures --staged reads the changed index blob.
        tracked.write_text("worktree safe", encoding="utf-8")
        result = self.check("--staged")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tracked.txt: possible credential/private key", result.stderr)
        self.assertNotIn(CANARY, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
