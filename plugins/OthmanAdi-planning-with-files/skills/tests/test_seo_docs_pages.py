"""Guards for the v3.8.0 problem-query docs pages.

The three pages under docs/ answer high-volume search queries and carry
strict content rules: fixed H1, 60-120 line budget, the two-route Install
section, cross-links between all three, links back to README and
docs/installation.md, internal-v1 framing on any recovery number, no
em/en dashes, and no competitor method names. This test pins each rule
so later edits cannot silently break them.
"""
from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = REPO_ROOT / "docs"

# filename -> required exact H1 (first line of the file)
PAGES = {
    "claude-code-lost-context-after-compaction.md": (
        "# Claude Code lost context after compaction: how to recover and prevent it"
    ),
    "agent-forgets-plan-after-clear.md": (
        "# My coding agent forgets the plan after /clear: the file-based fix"
    ),
    "long-running-agent-tasks.md": (
        "# Long-running agent tasks: keeping a coding agent on track for hours"
    ),
}

PLUGIN_MARKETPLACE = "/plugin marketplace add OthmanAdi/planning-with-files"
PLUGIN_INSTALL = "/plugin install planning-with-files@planning-with-files"
NPX_ONE_LINER = (
    "npx skills add OthmanAdi/planning-with-files --skill planning-with-files -g"
)

# Honesty rule for the release: competing planning methods are never named
# in SEO-facing docs pages.
COMPETITOR_NAMES = ("superpowers", "spec-kit", "memory-bank", "cline")


def read(name: str) -> str:
    return (DOCS_DIR / name).read_text(encoding="utf-8")


class SeoDocsPagesTests(unittest.TestCase):
    def test_pages_exist(self) -> None:
        for name in PAGES:
            self.assertTrue((DOCS_DIR / name).is_file(), name)

    def test_line_budget_60_to_120(self) -> None:
        for name in PAGES:
            count = len(read(name).splitlines())
            self.assertGreaterEqual(count, 60, f"{name}: {count} lines")
            self.assertLessEqual(count, 120, f"{name}: {count} lines")

    def test_exact_h1_on_first_line(self) -> None:
        for name, h1 in PAGES.items():
            first = read(name).splitlines()[0]
            self.assertEqual(first, h1, name)

    def test_install_section_with_both_routes(self) -> None:
        for name in PAGES:
            body = read(name)
            self.assertIn("## Install", body, name)
            install = body.split("## Install", 1)[1]
            self.assertIn(PLUGIN_MARKETPLACE, install, name)
            self.assertIn(PLUGIN_INSTALL, install, name)
            self.assertIn(NPX_ONE_LINER, install, name)

    def test_links_to_readme_and_installation_guide(self) -> None:
        for name in PAGES:
            body = read(name)
            self.assertIn("../README.md", body, f"{name}: missing README link")
            self.assertIn(
                "(installation.md)", body, f"{name}: missing docs/installation.md link"
            )

    def test_pages_cross_link_each_other(self) -> None:
        for name in PAGES:
            body = read(name)
            for other in PAGES:
                if other == name:
                    continue
                self.assertIn(other, body, f"{name} must link to {other}")

    def test_no_em_or_en_dashes(self) -> None:
        for name in PAGES:
            body = read(name)
            self.assertNotIn("—", body, f"{name}: em dash found")
            self.assertNotIn("–", body, f"{name}: en dash found")

    def test_recovery_number_keeps_internal_v1_framing(self) -> None:
        # Wherever the 5.0 vs 13.3 turn numbers appear, the internal-v1
        # framing must appear on the same page.
        for name in PAGES:
            body = read(name)
            if "5.0 turns" in body or "13.3" in body:
                low = body.lower()
                self.assertIn("internal", low, name)
                self.assertIn("v1", low, name)
                self.assertIn("author-run", low, name)

    def test_no_competitor_names(self) -> None:
        for name in PAGES:
            low = read(name).lower()
            for competitor in COMPETITOR_NAMES:
                self.assertNotIn(competitor, low, f"{name}: names {competitor}")


if __name__ == "__main__":
    unittest.main()
