"""BOM-prefixed shell pointers retain their bytes in display and listing modes."""
from __future__ import annotations

import codecs
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "set-active-plan.sh"
SH = shutil.which("sh")


@pytest.mark.skipif(SH is None, reason="requires a POSIX sh")
@pytest.mark.parametrize("ending", [b"", b"\n", b"\r\n"], ids=["no-newline", "lf", "crlf"])
def test_bom_pointer_display_and_listing_preserve_readonly_bytes(tmp_path, ending):
    plan = tmp_path / ".planning" / "alpha"
    plan.mkdir(parents=True)
    (plan / "task_plan.md").write_text("### Phase 1: Work [pending]\n", encoding="utf-8")
    pointer = tmp_path / ".planning" / ".active_plan"
    original_bytes = codecs.BOM_UTF8 + b"alpha" + ending
    pointer.write_bytes(original_bytes)
    original_mode = pointer.stat().st_mode
    original_mtime = pointer.stat().st_mtime_ns
    pointer.chmod(stat.S_IREAD)
    env = os.environ.copy()
    for name in ("PLAN_ID", "PWF_PLAN_ROOT", "PLANNING_DISABLED"):
        env.pop(name, None)
    try:
        for args in ([], ["--list"]):
            result = subprocess.run(
                [SH, str(SCRIPT), *args], cwd=tmp_path, env=env,
                capture_output=True, text=True, encoding="utf-8",
                timeout=60, check=False,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            assert not result.stderr.strip(), result.stderr
            if args:
                assert any(line.startswith("- alpha [active]")
                           for line in result.stdout.splitlines()), result.stdout
            else:
                assert "Active plan: alpha" in result.stdout, result.stdout
            assert pointer.read_bytes() == original_bytes
            assert pointer.stat().st_mtime_ns == original_mtime
    finally:
        pointer.chmod(original_mode)
