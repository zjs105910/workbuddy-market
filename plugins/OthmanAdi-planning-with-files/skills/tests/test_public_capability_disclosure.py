"""Public metadata must disclose material planning-with-files capabilities."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

SESSION_HISTORY_SKILLS = [
    "skills/planning-with-files/SKILL.md",
    ".agents/skills/planning-with-files/SKILL.md",
    ".codebuddy/skills/planning-with-files/SKILL.md",
    ".codex/skills/planning-with-files/SKILL.md",
    ".continue/skills/planning-with-files/SKILL.md",
    ".cursor/skills/planning-with-files/SKILL.md",
    ".factory/skills/planning-with-files/SKILL.md",
    ".gemini/skills/planning-with-files/SKILL.md",
    ".hermes/skills/planning-with-files/SKILL.md",
    ".mastracode/skills/planning-with-files/SKILL.md",
    ".opencode/skills/planning-with-files/SKILL.md",
    ".pi/skills/planning-with-files/SKILL.md",
]

GATED_SKILLS = [
    path
    for path in SESSION_HISTORY_SKILLS
    if path
    not in {
        ".continue/skills/planning-with-files/SKILL.md",
        ".gemini/skills/planning-with-files/SKILL.md",
    }
]


def _description(relative_path: str) -> str:
    text = (ROOT / relative_path).read_text(encoding="utf-8")
    match = re.search(r'^description:\s*["\']?(.*?)["\']?\s*$', text, re.MULTILINE)
    assert match, f"missing description in {relative_path}"
    return match.group(1)


def test_session_history_skill_descriptions_disclose_consent_boundary():
    for relative_path in SESSION_HISTORY_SKILLS:
        description = _description(relative_path)
        assert "selected project planning context" in description
        assert "Automatic recovery reads project planning files only" in description
        assert "--metadata" in description
        assert "--replay" in description
        assert "commands declared in Markdown" in description
        assert "no network upload path" in description


def test_continuation_disclosure_matches_adapter_capability():
    for relative_path in GATED_SKILLS:
        description = _description(relative_path)
        assert "Optional gated mode can request continuation only when the host supports it" in description

    continue_description = _description(".continue/skills/planning-with-files/SKILL.md")
    assert "registers no lifecycle or Stop hook" in continue_description
    assert "never requests continuation" in continue_description

    gemini_description = _description(".gemini/skills/planning-with-files/SKILL.md")
    assert "session-end hook reports status only" in gemini_description
    assert "does not request continuation" in gemini_description


def test_kiro_description_discloses_file_only_recovery():
    description = _description(".kiro/skills/planning-with-files/SKILL.md")
    assert "Kiro skill instructions and steering state read selected project planning context" in description
    assert "timestamps only, not agent transcript stores" in description
    assert "registers no Stop hook" in description
    assert "never requests continuation" in description
    assert "never runs commands declared in Markdown" in description
    assert "no network upload path" in description


def test_plugin_metadata_discloses_material_capabilities():
    metadata = [
        json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["description"],
        json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))["description"],
        json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))["plugins"][0]["description"],
        json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))["description"],
        json.loads((ROOT / ".pi/skills/planning-with-files/package.json").read_text(encoding="utf-8"))["description"],
    ]

    for description in metadata:
        assert "project" in description.lower()
        assert "context" in description.lower()
        assert "network upload path" in description.lower()
