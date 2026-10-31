"""Relative links must work when only the advertised skill directory is installed."""

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("relative", [
    "skills/planning-with-files",
    ".agents/skills/planning-with-files",
    ".pi/skills/planning-with-files",
])
def test_skill_links_resolve_inside_the_standalone_package(relative):
    skill = ROOT / relative
    source = (skill / "SKILL.md").read_text(encoding="utf-8")
    local = []
    for href in re.findall(r"\[[^\]\n]+\]\(([^)\s]+)\)", source):
        parsed = urlsplit(href)
        if parsed.scheme or parsed.netloc or not parsed.path:
            continue
        target = (skill / unquote(parsed.path)).resolve()
        assert target.is_relative_to(skill.resolve()), f"{relative}: outside package: {href}"
        assert target.is_file(), f"{relative}: missing referenced file: {href}"
        local.append(target)
    # The template and examples/reference links must actually be exercised.
    assert len(local) >= 5
