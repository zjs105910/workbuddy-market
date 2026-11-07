"""Automatic lifecycle callers must never opt into local session history."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_shell_and_powershell_session_start_callers_are_zero_history():
    callers = {
        "hooks/claude-hook.sh": '"$SESSION_CATCHUP" --no-history',
        ".codex/hooks/session-start.sh": 'session-catchup.py" --no-history',
        ".gemini/hooks/session-start.sh": 'session-catchup.py" --no-history',
        ".github/hooks/scripts/session-start.sh": 'session-catchup.py" --no-history',
        ".github/hooks/scripts/session-start.ps1": 'session-catchup.py" --no-history',
    }

    for relative, expected in callers.items():
        source = (ROOT / relative).read_text(encoding="utf-8")
        assert expected in source, relative
        assert 'session-catchup.py" --metadata' not in source, relative
        assert 'session-catchup.py" --replay' not in source, relative


def test_pi_lifecycle_caller_is_zero_history():
    source = (
        ROOT
        / ".pi/skills/planning-with-files/extensions/planning-with-files/runtime.ts"
    ).read_text(encoding="utf-8")
    assert source.count('CATCHUP_SCRIPT, "--no-history", cwd') == 4
    assert 'CATCHUP_SCRIPT, "--metadata"' not in source
    assert 'CATCHUP_SCRIPT, "--replay"' not in source
