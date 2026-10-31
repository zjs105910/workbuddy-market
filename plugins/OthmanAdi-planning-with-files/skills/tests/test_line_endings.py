"""Line-ending guard for the CRLF silent-kill class.

A POSIX sh script that reaches disk with CRLF endings dies at the shebang
("/bin/sh^M: bad interpreter") or on the first backslash continuation, and
the hook dispatchers wrap every call in fallbacks that swallow the error,
so planning hooks stop firing with no visible symptom. Python scripts with
a CRLF shebang fail the same way when invoked as executables. The root
.gitattributes pins *.sh and *.py to eol=lf so no checkout, zip download,
or contributor core.autocrlf setting can reintroduce CRLF.

The authoritative assertion runs against the git INDEX via the i/<eolinfo>
column of `git ls-files --eol`, not against raw working-tree bytes: on a
machine with core.autocrlf=true, a checkout that predates .gitattributes
legitimately shows CRLF in the working tree for blobs stored as LF, and
only the committed bytes decide what every other machine receives. A raw
byte pass over the checked-out files runs additionally wherever
core.autocrlf is not "true" (the ubuntu CI leg at minimum).
"""
from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GITATTRIBUTES = REPO_ROOT / ".gitattributes"

# eolinfo values whose content cannot contain a carriage return: pure-LF
# files and files with no line endings at all.
CLEAN_INDEX_EOL = {"i/lf", "i/none"}


def _run_git(args):
    """stdout of a git command at the repo root, or None when git is
    unavailable, this is not a git checkout, or the command fails."""
    try:
        proc = subprocess.run(
            ["git", "-c", "core.quotepath=off", *args],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _eol_entries():
    """(index_eol, worktree_eol, path) for every tracked *.sh and *.py
    file, from `git ls-files --eol`. None when git is unavailable."""
    out = _run_git(["ls-files", "--eol", "--", "*.sh", "*.py"])
    if out is None:
        return None
    entries = []
    for line in out.splitlines():
        if not line.strip():
            continue
        info, sep, path = line.partition("\t")
        if not sep:
            continue
        # Line format: i/<eolinfo> w/<eolinfo> attr/<attrs><TAB><path>.
        # The attr field contains spaces once attributes are set, so only
        # the two leading tokens are positional.
        tokens = info.split()
        if len(tokens) < 2 or not tokens[0].startswith("i/"):
            continue
        entries.append((tokens[0], tokens[1], path.strip()))
    return entries


class LineEndingTests(unittest.TestCase):
    def test_gitattributes_pins_sh_and_py_to_lf(self):
        self.assertTrue(
            GITATTRIBUTES.is_file(),
            ".gitattributes missing at repo root; nothing prevents CRLF "
            "from reaching tracked hook scripts",
        )
        rules = set()
        for raw in GITATTRIBUTES.read_text(encoding="utf-8").splitlines():
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            rules.add(" ".join(stripped.split()))
        self.assertIn(
            "*.sh text eol=lf",
            rules,
            ".gitattributes lost the '*.sh text eol=lf' rule",
        )
        self.assertIn(
            "*.py text eol=lf",
            rules,
            ".gitattributes lost the '*.py text eol=lf' rule",
        )

    def test_tracked_sh_and_py_are_lf_in_index(self):
        entries = _eol_entries()
        if entries is None:
            self.skipTest("git unavailable or not a git checkout")
        self.assertTrue(
            entries,
            "git ls-files enumerated no tracked *.sh or *.py files; the "
            "pathspec or parser is broken, not the repo",
        )
        offenders = [
            f"{path} ({index_eol})"
            for index_eol, _worktree_eol, path in entries
            if index_eol not in CLEAN_INDEX_EOL
        ]
        self.assertEqual(
            [],
            offenders,
            "scripts committed with CRLF or binary content in the git "
            "index; these bytes ship to every checkout: "
            + ", ".join(offenders),
        )

    def test_tracked_sh_and_py_worktree_bytes_have_no_cr(self):
        entries = _eol_entries()
        if entries is None:
            self.skipTest("git unavailable or not a git checkout")
        autocrlf = _run_git(["config", "--get", "core.autocrlf"])
        if autocrlf is not None and autocrlf.strip().lower() == "true":
            # A checkout made before .gitattributes existed holds CRLF
            # smudged from LF blobs; the index test above stays
            # authoritative on such machines.
            self.skipTest("core.autocrlf=true; working tree may be smudged")
        offenders = []
        for _index_eol, _worktree_eol, rel_path in entries:
            path = REPO_ROOT / rel_path
            if not path.is_file():
                continue
            if b"\r" in path.read_bytes():
                offenders.append(rel_path)
        self.assertEqual(
            [],
            offenders,
            "checked-out script bytes contain CR: " + ", ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
