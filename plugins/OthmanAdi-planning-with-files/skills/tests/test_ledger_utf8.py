"""UTF-8 safety of the run-ledger summary truncation.

ledger-append.sh truncates SUMMARY with cut -c1-200. GNU cut -c counts BYTES,
so a CJK or emoji summary could be clipped mid-codepoint, leaving a ledger
line that strict UTF-8 readers reject. The script now strips any trailing
incomplete UTF-8 sequence after truncation: iconv -c when available, a
byte-level od fallback otherwise. ledger-append.ps1 truncates with char-based
Substring and needs no repair; it is exercised here for parity.

Four legs:
  * sh, iconv path (default PATH; glibc, macOS, Git for Windows ship iconv)
  * sh, fallback path (a failing iconv shim forces the byte-level trim)
  * sh, degraded path (iconv and od both failing: the summary passes through
    unchanged rather than the append failing or losing the summary)
  * PowerShell (pwsh or Windows PowerShell, whichever is present)

Every leg asserts the ledger line decodes as strict UTF-8, parses with
json.loads, and keeps the tick/agent fields intact.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "planning-with-files" / "scripts"
LEDGER_APPEND_SH = SCRIPTS_DIR / "ledger-append.sh"
LEDGER_APPEND_PS1 = SCRIPTS_DIR / "ledger-append.ps1"

SH = shutil.which("sh")
POWERSHELL = (
    shutil.which("pwsh")
    or shutil.which("powershell.exe")
    or shutil.which("powershell")
)

# 100 CJK chars at 3 UTF-8 bytes each: 300 bytes, the 200-byte cut lands two
# bytes into the 67th character.
CHINESE_300_BYTES = "你好" * 50
CHINESE_66_CHARS = "你好" * 33

# 4-byte emoji placed so the 200-byte cut keeps 3, 2, or 1 of its bytes.
EMOJI = "\U0001f600"
EMOJI_BOUNDARY_CASES = {
    "three_bytes_inside": "a" * 197,
    "two_bytes_inside": "a" * 198,
    "lead_byte_inside": "a" * 199,
}


def parse_ledger_lines(path: Path) -> list[dict]:
    """Strict UTF-8 decode plus json.loads for every non-empty ledger line.

    A clipped multibyte sequence raises UnicodeDecodeError here, which is the
    regression this file guards. Windows PowerShell 5.1 writes a BOM when it
    creates the file; that is valid UTF-8, so it is tolerated before parsing.
    """
    text = path.read_bytes().decode("utf-8")
    objs = []
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line:
            continue
        objs.append(json.loads(line))
    return objs


class LedgerUtf8Base(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="pwf-ledger-utf8-"))
        self.plan_dir = self.tmp / ".planning" / "p"
        self.plan_dir.mkdir(parents=True)
        (self.tmp / ".planning" / ".active_plan").write_text("p\n", encoding="utf-8")
        (self.plan_dir / "task_plan.md").write_text(
            "# Task Plan\n"
            "### Phase 1: Build\n"
            "- **Status:** in_progress\n",
            encoding="utf-8",
        )
        self.env = os.environ.copy()
        self.env.pop("PLAN_ID", None)

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def append_sh(self, *args: str):
        return subprocess.run(
            ["sh", str(LEDGER_APPEND_SH), *args],
            cwd=str(self.tmp),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=self.env,
            check=False,
        )


@unittest.skipUnless(SH, "sh not available on this platform")
class ShIconvPathTests(LedgerUtf8Base):
    """Default PATH: the iconv -c repair path on every supported platform."""

    def test_chinese_300_byte_summary_is_strict_utf8(self) -> None:
        result = self.append_sh("progress", CHINESE_300_BYTES, "--agent", "main")
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual(1, len(objs))
        obj = objs[0]
        self.assertEqual(1, obj["tick"])
        self.assertEqual("main", obj["agent"])
        # GNU cut clips at 200 bytes: 66 whole chars survive. BSD cut clips at
        # 200 chars: the 100-char summary is untouched. Both must be valid.
        self.assertIn(obj["summary"], {CHINESE_66_CHARS, CHINESE_300_BYTES})
        self.assertNotIn("\ufffd", obj["summary"])
        self.assertLessEqual(len(obj["summary"]), 200)

    def test_emoji_spanning_byte_boundary(self) -> None:
        for name, prefix in EMOJI_BOUNDARY_CASES.items():
            with self.subTest(case=name):
                summary = prefix + EMOJI + "tail"
                result = self.append_sh("progress", summary, "--agent", "main")
                self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual(len(EMOJI_BOUNDARY_CASES), len(objs))
        for obj, prefix in zip(objs, EMOJI_BOUNDARY_CASES.values()):
            self.assertEqual("main", obj["agent"])
            self.assertNotIn("\ufffd", obj["summary"])
            # GNU: the clipped emoji bytes are stripped, the ASCII prefix
            # stays. BSD: the whole emoji fits the 200-char budget.
            self.assertTrue(obj["summary"].startswith(prefix), obj["summary"])
            self.assertLessEqual(len(obj["summary"]), 200)

    def test_complete_multibyte_char_at_boundary_survives(self) -> None:
        # Exactly 200 bytes ending in a complete 3-byte char: no repair may
        # remove it on either the iconv path or the fallback path.
        summary = "a" * 197 + "你"
        result = self.append_sh("progress", summary, "--agent", "main")
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual(summary, objs[0]["summary"])

    def test_ascii_truncation_budget_unchanged(self) -> None:
        result = self.append_sh("progress", "x" * 300, "--agent", "main")
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual("x" * 200, objs[0]["summary"])

    def test_tick_scan_survives_multibyte_lines(self) -> None:
        # The sed-based tick scan must keep counting after a CJK-laden line.
        self.append_sh("progress", CHINESE_300_BYTES, "--agent", "main")
        result = self.append_sh("note", "plain follow-up", "--agent", "main")
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual([1, 2], [obj["tick"] for obj in objs])


@unittest.skipUnless(SH, "sh not available on this platform")
class ShFallbackPathTests(LedgerUtf8Base):
    """A failing iconv shim forces the byte-level od fallback in the script.

    The shim exits 1 with empty output, the exact signature the script treats
    as an unusable iconv. cygwin/msys and POSIX both execute the shebang file.
    """

    def setUp(self) -> None:
        super().setUp()
        shim_dir = self.tmp / "shim"
        shim_dir.mkdir()
        shim = shim_dir / "iconv"
        shim.write_text("#!/bin/sh\nexit 1\n", encoding="ascii", newline="\n")
        os.chmod(shim, 0o755)
        self.env["PATH"] = str(shim_dir) + os.pathsep + self.env.get("PATH", "")

    def test_chinese_300_byte_summary_is_strict_utf8(self) -> None:
        result = self.append_sh("progress", CHINESE_300_BYTES, "--agent", "main")
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertIn(objs[0]["summary"], {CHINESE_66_CHARS, CHINESE_300_BYTES})
        self.assertEqual(1, objs[0]["tick"])
        self.assertEqual("main", objs[0]["agent"])

    def test_emoji_spanning_byte_boundary(self) -> None:
        for name, prefix in EMOJI_BOUNDARY_CASES.items():
            with self.subTest(case=name):
                summary = prefix + EMOJI + "tail"
                result = self.append_sh("progress", summary, "--agent", "main")
                self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual(len(EMOJI_BOUNDARY_CASES), len(objs))
        for obj, prefix in zip(objs, EMOJI_BOUNDARY_CASES.values()):
            self.assertNotIn("\ufffd", obj["summary"])
            self.assertTrue(obj["summary"].startswith(prefix), obj["summary"])

    def test_complete_multibyte_char_at_boundary_survives(self) -> None:
        summary = "a" * 197 + "你"
        result = self.append_sh("progress", summary, "--agent", "main")
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual(summary, objs[0]["summary"])

    def test_ascii_truncation_budget_unchanged(self) -> None:
        result = self.append_sh("progress", "x" * 300, "--agent", "main")
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual("x" * 200, objs[0]["summary"])


@unittest.skipUnless(SH, "sh not available on this platform")
class ShDegradedToolingTests(LedgerUtf8Base):
    """iconv and od both failing: repair degrades to passthrough.

    tests/test_bsd_userland_sim.py runs the scripts on a PATH with only an
    enumerated toolset, without iconv, od, dd, or wc. The repair must then
    pass the summary through unchanged instead of failing the append or
    emptying the summary. Failing shims reach the same passthrough branch
    without replacing PATH wholesale, which MSYS on Windows cannot survive.
    """

    def setUp(self) -> None:
        super().setUp()
        shim_dir = self.tmp / "shim"
        shim_dir.mkdir()
        for tool in ("iconv", "od"):
            shim = shim_dir / tool
            shim.write_text("#!/bin/sh\nexit 1\n", encoding="ascii", newline="\n")
            os.chmod(shim, 0o755)
        self.env["PATH"] = str(shim_dir) + os.pathsep + self.env.get("PATH", "")

    def test_ascii_summary_still_truncated_and_valid(self) -> None:
        result = self.append_sh("progress", "x" * 300, "--agent", "main")
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual("x" * 200, objs[0]["summary"])
        self.assertEqual(1, objs[0]["tick"])
        self.assertEqual("main", objs[0]["agent"])

    def test_short_multibyte_summary_passes_through(self) -> None:
        # Under the 200 budget nothing is clipped, so passthrough keeps the
        # summary byte-identical and the line valid.
        summary = "你好" * 10
        result = self.append_sh("progress", summary, "--agent", "main")
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual(summary, objs[0]["summary"])


@unittest.skipUnless(POWERSHELL, "PowerShell not available on this platform")
class Ps1CharBudgetTests(LedgerUtf8Base):
    """The ps1 twin truncates by characters; multibyte input stays intact."""

    def append_ps1(self, *args: str):
        return subprocess.run(
            [
                POWERSHELL,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(LEDGER_APPEND_PS1),
                *args,
            ],
            cwd=str(self.tmp),
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            env=self.env,
            check=False,
        )

    def test_chinese_300_byte_summary_survives_untruncated(self) -> None:
        # 100 chars is under the 200-character budget: no truncation at all.
        result = self.append_ps1("progress", CHINESE_300_BYTES)
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual(1, len(objs))
        self.assertEqual(1, objs[0]["tick"])
        self.assertEqual("main", objs[0]["agent"])
        self.assertEqual(CHINESE_300_BYTES, objs[0]["summary"])

    def test_chinese_300_char_summary_truncates_to_200_chars(self) -> None:
        result = self.append_ps1("progress", "你" * 300)
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual("你" * 200, objs[0]["summary"])

    def test_emoji_at_char_boundary_stays_strict_utf8(self) -> None:
        # The emoji is a surrogate pair; a 200-unit Substring can split it.
        # The UTF-8 encoder then substitutes U+FFFD, which is still valid
        # UTF-8, so the line must decode strictly and parse either way.
        summary = "a" * 199 + EMOJI + "tail"
        result = self.append_ps1("progress", summary)
        self.assertEqual(0, result.returncode, result.stderr)
        objs = parse_ledger_lines(self.plan_dir / "ledger-main.jsonl")
        self.assertEqual(1, objs[0]["tick"])
        self.assertEqual("main", objs[0]["agent"])
        self.assertTrue(objs[0]["summary"].startswith("a" * 199))
        self.assertLessEqual(len(objs[0]["summary"]), 200)


if __name__ == "__main__":
    unittest.main()
