"""Encoding guard for the Windows PowerShell 5.1 silent-kill class.

Windows PowerShell 5.1 (`powershell.exe`, still the default shell on Windows
and the interpreter every hook dispatcher reaches for first) reads a `.ps1`
file as ANSI (CP1252 on a western install) unless the file carries a UTF-8
BOM. PowerShell 7 (`pwsh`) assumes UTF-8 either way, so a BOM-less script
holding non-ASCII text parses on the developer's machine and dies on the
user's.

It dies rather than merely garbling because of which bytes land where. The
UTF-8 encoding of an em dash is E2 80 94, and CP1252 maps 0x94 to a curly
closing double quote, so the character opens a string literal that never
closes. Arrows (U+2192, ending in 0x92, a curly apostrophe) do the same. The
failure is a parse error before the first statement runs, and every hook
dispatcher in this repo wraps its PowerShell call in fallbacks that swallow
the error, so planning hooks simply stop firing with no visible symptom.

Measured at v3.8.2, eight shipped scripts failed to parse under 5.1:
`.cursor/hooks/user-prompt-submit.ps1` (the Cursor plan injection hook), both
`.kiro` asset scripts, the Arabic `check-complete.ps1`, and `check-complete`
plus `init-session` for both Chinese variants. The Chinese `init-session.ps1`
meant a Windows user of that variant could not create a plan at all.

The invariant is therefore: a tracked `.ps1` containing any byte above 0x7F
must begin with a UTF-8 BOM. Pure-ASCII scripts need nothing, which is why
the canonical English scripts are exempt and stay byte-identical to their
mirrored copies.
"""
from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
UTF8_BOM = b"\xef\xbb\xbf"


def _tracked_ps1() -> list[Path]:
    """Every .ps1 tracked by git, or [] when this is not a git checkout."""
    try:
        proc = subprocess.run(
            ["git", "ls-files", "*.ps1"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [REPO_ROOT / line for line in proc.stdout.split() if line]


def _windows_powershell() -> str | None:
    """Path to Windows PowerShell 5.1, which is the interpreter that actually
    has the ANSI default. pwsh is deliberately NOT accepted here: it parses
    BOM-less UTF-8 correctly and would make this check pass vacuously."""
    return shutil.which("powershell.exe") or shutil.which("powershell")


class Ps1EncodingTests(unittest.TestCase):
    def test_repo_has_tracked_ps1_files(self) -> None:
        # Guard against the whole suite passing because the glob found nothing.
        self.assertTrue(_tracked_ps1(), "expected tracked .ps1 files in the repo")

    def test_non_ascii_ps1_carries_utf8_bom(self) -> None:
        for path in _tracked_ps1():
            data = path.read_bytes()
            if all(byte < 0x80 for byte in data):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            with self.subTest(script=rel):
                self.assertTrue(
                    data.startswith(UTF8_BOM),
                    f"{rel} holds non-ASCII but has no UTF-8 BOM, so Windows "
                    f"PowerShell 5.1 reads it as ANSI and can fail to parse it",
                )

    def test_bom_is_not_added_to_pure_ascii_scripts(self) -> None:
        # A blanket "BOM everything" fix would break the byte-identity the
        # dual-shipped script parity tests enforce, so keep ASCII files bare.
        for path in _tracked_ps1():
            data = path.read_bytes()
            if not data.startswith(UTF8_BOM):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            with self.subTest(script=rel):
                self.assertFalse(
                    all(byte < 0x80 for byte in data[len(UTF8_BOM):]),
                    f"{rel} is pure ASCII and does not need a BOM",
                )


@unittest.skipUnless(_windows_powershell(), "Windows PowerShell 5.1 not available")
class Ps1ParseTests(unittest.TestCase):
    """The direct proof: ask the real interpreter to parse every script.

    ParseFile applies the same encoding detection as execution, so this
    catches any encoding trap, not only the BOM one the guard above covers.
    """

    def test_every_ps1_parses_under_windows_powershell(self) -> None:
        scripts = _tracked_ps1()
        self.assertTrue(scripts, "expected tracked .ps1 files in the repo")
        shell = _windows_powershell()
        assert shell is not None  # guaranteed by the class-level skipUnless
        command = (
            "$bad = @(); "
            "foreach ($f in $input) { "
            "  $errors = $null; "
            "  $null = [System.Management.Automation.Language.Parser]::ParseFile("
            "$f, [ref]$null, [ref]$errors); "
            "  if ($errors -and $errors.Count -gt 0) { "
            "    $bad += ('{0} :: {1}' -f $f, $errors[0].Message) } }; "
            "$bad -join \"`n\""
        )
        proc = subprocess.run(
            [shell, "-NoProfile", "-ExecutionPolicy", "RemoteSigned",
             "-Command", command],
            input="\n".join(str(p) for p in scripts),
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        failures = (proc.stdout or "").strip()
        self.assertEqual(
            failures,
            "",
            f"PowerShell scripts failed to parse under Windows PowerShell:\n{failures}",
        )


if __name__ == "__main__":
    unittest.main()
