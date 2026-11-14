from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_HOSTS = (
    "Claude Code",
    "Hermes Agent",
    "OpenClaw",
    "Codex",
    "DeepSeek Harness",
    "Pi coding agent",
    "Grok Build",
    "OpenCode",
)
HOST_LOGO_FILES = (
    "claude-code-wordmark-dark.svg",
    "claude-code-wordmark-light.svg",
    "hermes-agent-wordmark.png",
    "openclaw-wordmark-dark.svg",
    "openclaw-wordmark-light.svg",
    "codex-mark-dark.png",
    "codex-mark-light.png",
    "deepseek-wordmark-dark.svg",
    "deepseek-wordmark-light.svg",
    "pi-mark.svg",
    "grok-build-mark-dark.png",
    "grok-build-mark-light.png",
    "opencode-wordmark-dark.svg",
    "opencode-wordmark-light.svg",
)
# Slash invocations start at a text boundary; slashes inside install paths are allowed.
README_INVOCATION_PATTERNS = (
    re.compile(r"\$distilly\b"),
    re.compile(r"@distilly\b"),
    re.compile(r"(?<![\w.-])/distilly\b"),
    re.compile(r"(?<![\w.-])/skill(?:\s+|:)distilly\b"),
    re.compile(r"(?<![\w.-])/skills\b"),
    re.compile(r"(?<![\w.-])/\{character\}-\{slug\}"),
    re.compile(r"\$\{character\}-\{slug\}"),
    re.compile(r"(?<![\w.-])/skill:\{character\}-\{slug\}"),
)
HAN_CHARACTER = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


class SkillEntrypointDocsTest(unittest.TestCase):
    def _assert_readme_support_contract(self, content: str, source: str) -> None:
        self.assertIn("### 3️⃣", content, f"missing host section in {source}")
        host_section = content.split("### 3️⃣", 1)[1].split("\n---", 1)[0]
        host_rows = re.findall(r'<img [^>]*alt="([^"]+)"', host_section)

        self.assertEqual(list(SUPPORTED_HOSTS), host_rows, f"wrong host list in {source}")
        self.assertNotIn("🟣 **Claude Code**", host_section, f"text host rows remain in {source}")
        self.assertNotIn(
            "img.shields.io/badge/Claude%20Code-Skill",
            content,
            f"duplicate host badges remain in {source}",
        )
        logo_prefix = "docs/assets/hosts/" if source == "README.md" else "../assets/hosts/"
        for logo_file in HOST_LOGO_FILES:
            self.assertIn(logo_prefix + logo_file, host_section, f"missing {logo_file} in {source}")
        self.assertIn("Grok Bot", host_section, f"missing Grok Bot preview in {source}")
        self.assertIn("{character}-{slug}", content, f"missing generated Skill name in {source}")
        self.assertNotIn("## 📂", content, f"project structure section remains in {source}")
        for pattern in README_INVOCATION_PATTERNS:
            self.assertIsNone(
                pattern.search(content),
                f"invocation tutorial matching {pattern.pattern!r} remains in {source}",
            )

    def _assert_readme_quick_start(
        self, content: str, source: str, install_link: str
    ) -> None:
        self.assertIn("## ⚡", content, f"missing install section in {source}")
        quick_start = content.split("## ⚡", 1)[1].split("\n## ✨", 1)[0]
        self.assertIn("### 🤖", quick_start, f"missing Agent path in {source}")
        self.assertIn("### 👤", quick_start, f"missing human path in {source}")
        self.assertIn(
            "git clone https://github.com/titanwings/distilly "
            "<DISTILLY_SKILL_DIR>",
            quick_start,
            f"missing short clone command in {source}",
        )
        self.assertIn(install_link, quick_start, f"missing install guide link in {source}")
        self.assertIn("{character}-{slug}", quick_start)
        self.assertNotIn("<details>", quick_start, f"collapsed install table remains in {source}")
        self.assertNotIn(
            "tools/install_generated_skill.py",
            quick_start,
            f"generated Skill installer detail remains in {source}",
        )
        self.assertNotIn(
            "tools/research/",
            quick_start,
            f"celebrity research commands remain in {source}",
        )

    def test_root_skill_uses_distilly_entrypoint(self) -> None:
        content = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("name: distilly", content)
        self.assertIn("`/distilly`", content)
        self.assertIn("`$distilly`", content)
        self.assertIn("`/skill:distilly`", content)
        self.assertNotIn("name: dot-skill", content)
        self.assertNotIn("`/dot-skill`", content)
        self.assertIn("兼容宿主", content)
        self.assertIn("compatible hosts", content.lower())
        self.assertIn("Grok Build", content)
        self.assertIn("Grok Bot", content)
        self.assertIn("Pi coding agent", content)
        self.assertIn("管理操作", content)
        self.assertIn("tools/skill_writer.py", content)
        self.assertIn("tools/research/xquik_public_posts.py", content)
        self.assertIn("prompts/celebrity/research.md", content)
        self.assertIn("budget-unfriendly", content)
        self.assertIn("references/celebrity_budget_unfriendly_framework.md", content)
        self.assertIn("01_core_profile.md", content)
        self.assertIn("03_expression_and_reception.md", content)
        self.assertIn("Files scanned >= 3", content)
        self.assertIn("Unique URLs >= 2", content)
        self.assertIn("Potential long quote lines = 0", content)
        self.assertIn("实际打开过的具体页面", content)
        self.assertIn("actual inspected pages", content)
        self.assertIn("01_writings.md", content)
        self.assertIn("06_timeline.md", content)
        self.assertIn("Files scanned >= 6", content)
        self.assertIn("Unique URLs >= 8", content)
        self.assertIn("Primary-source markers >= 3", content)
        self.assertIn("research_audit.md", content)
        self.assertIn("--work-patch /tmp/distilly_{slug}_work_patch.md", content)
        self.assertIn("Do not hand-edit `work.md`", content)
        self.assertIn("{distilly_skill_root}", content)
        self.assertIn("${CLAUDE_SKILL_DIR}", content)
        self.assertIn("Do not assume the shell's current working directory", content)
        self.assertNotIn("python3 tools/", content)
        self.assertNotIn("`/list-skills`", content)
        self.assertNotIn("Compatibility aliases:", content)

    def test_readme_quick_start_and_install_detail_contract(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        install = (ROOT / "INSTALL.md").read_text(encoding="utf-8")
        install_en = (ROOT / "INSTALL_EN.md").read_text(encoding="utf-8")
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")

        self._assert_readme_support_contract(readme, "README.md")
        self._assert_readme_quick_start(readme, "README.md", "(INSTALL_EN.md)")
        self.assertNotIn("/dot-skill", readme)
        self.assertNotIn("skills/dot-skill", readme)
        self.assertIn("https://github.com/titanwings/distilly", readme)
        self.assertNotIn("https://github.com/titanwings/colleague-skill", readme)

        self.assertIn(".claude/skills/distilly", install)
        self.assertIn("~/.openclaw/workspace/skills/distilly", install)
        self.assertIn("~/.agents/skills/distilly", install)
        self.assertIn("~/.dsh/skills/distilly", install)
        self.assertIn("~/.pi/agent/skills/distilly", install)
        self.assertIn("~/.grok/skills/distilly", install)
        self.assertIn("~/.config/opencode/skills/distilly", install)
        self.assertIn(".opencode/skills/distilly", install)
        self.assertIn("/distilly", install)
        self.assertNotIn("/dot-skill", install)
        self.assertNotIn("skills/dot-skill", install)
        self.assertIn("https://github.com/titanwings/distilly", install)
        self.assertNotIn("https://github.com/titanwings/colleague-skill", install)
        self.assertIn("./skills/colleague", install)
        self.assertIn("install_claude_generated_skill.py", install)
        self.assertIn("install_openclaw_generated_skill.py", install)
        self.assertIn("install_codex_generated_skill.py", install)
        self.assertIn("install_openclaw_skill.py", install)
        self.assertIn("install_codex_skill.py", install)
        self.assertIn("tools/research/quality_check.py", install)
        self.assertIn("tools/research/xquik_public_posts.py", install)
        self.assertIn("tools/research/download_subtitles.sh", install)
        self.assertIn("tools/research/merge_research.py", install)
        self.assertIn("pip3 install -r requirements.txt", install)
        self.assertIn("pip3 install yt-dlp", install)
        self.assertIn("~/.claude/skills/distilly", install_en)
        self.assertIn("~/.openclaw/workspace/skills/distilly", install_en)
        self.assertIn("~/.hermes/skills/openclaw-imports/distilly", install_en)
        self.assertIn("~/.agents/skills/distilly", install_en)
        self.assertIn("~/.dsh/skills/distilly", install_en)
        self.assertIn("~/.pi/agent/skills/distilly", install_en)
        self.assertIn("~/.grok/skills/distilly", install_en)
        self.assertIn("~/.config/opencode/skills/distilly", install_en)
        self.assertIn("tools/install_generated_skill.py", install_en)
        self.assertIn("tools/research/download_subtitles.sh", install_en)
        self.assertIn("tools/research/srt_to_transcript.py", install_en)
        self.assertIn("tools/research/merge_research.py", install_en)
        self.assertIn("tools/research/quality_check.py", install_en)
        self.assertIn("pip3 install -r requirements.txt", install_en)
        self.assertIn("pip3 install yt-dlp", install_en)
        self.assertIn("/{character}-{slug}", install)
        self.assertIn("./skills/colleague", skill)
        self.assertIn("DeepSeek Harness", skill)
        self.assertIn("OpenCode", skill)
        self.assertIn("eight agent hosts", readme.lower())
        self.assertIn("兼容宿主", install)

        for logo_file in HOST_LOGO_FILES:
            self.assertTrue((ROOT / "docs" / "assets" / "hosts" / logo_file).is_file())

    def test_repo_examples_live_under_skills_colleague(self) -> None:
        self.assertTrue((ROOT / "skills" / "colleague" / "example_zhangsan").exists())
        self.assertTrue((ROOT / "skills" / "colleague" / "example_tianyi").exists())
        self.assertTrue((ROOT / "skills" / "colleague" / "example_jiaxiu").exists())
        self.assertFalse((ROOT / "colleagues").exists())

    def test_multilingual_readmes_list_hosts_without_invocation_tutorials(self) -> None:
        for readme_path in (ROOT / "docs" / "lang").glob("README_*.md"):
            content = readme_path.read_text(encoding="utf-8")
            self.assertNotIn("/dot-skill", content, f"stale /dot-skill in {readme_path.name}")
            self._assert_readme_support_contract(content, readme_path.name)
            self._assert_readme_quick_start(
                content,
                readme_path.name,
                "(../../INSTALL.md)"
                if readme_path.name == "README_ZH.md"
                else "(../../INSTALL_EN.md)",
            )
            self.assertIn(
                "https://github.com/titanwings/distilly",
                content,
                f"missing published repository URL in {readme_path.name}",
            )
            self.assertNotIn(
                "https://github.com/titanwings/colleague-skill",
                content,
                f"stale repository URL in {readme_path.name}",
            )
            self.assertNotIn(
                "colleague_skill.pdf",
                content,
                f"broken local paper link in {readme_path.name}",
            )

    def test_non_chinese_docs_call_the_product_lark(self) -> None:
        non_chinese = [ROOT / "README.md", ROOT / "docs" / "lang" / "README_EN.md"]
        non_chinese.extend(
            ROOT / "docs" / "lang" / f"README_{language}.md"
            for language in ("DE", "ES", "JA", "KO", "PT", "RU")
        )
        for path in non_chinese:
            content = path.read_text(encoding="utf-8")
            self.assertIn("Lark", content, f"missing Lark in {path.name}")
            self.assertNotIn("Feishu", content, f"stale visible Feishu name in {path.name}")

        chinese = (ROOT / "docs" / "lang" / "README_ZH.md").read_text(encoding="utf-8")
        self.assertIn("飞书", chinese)

    def test_non_chinese_surfaces_do_not_mix_chinese_copy(self) -> None:
        single_language_paths = [
            ROOT / "README.md",
            ROOT / "ROADMAP.md",
            ROOT / "CONTRIBUTING.md",
            ROOT / "CITATION.cff",
            ROOT / "INSTALL_EN.md",
            ROOT / "docs" / "lang" / "README_EN.md",
            ROOT / "prompts" / "celebrity" / "research.md",
            ROOT / "prompts" / "celebrity" / "budget_unfriendly" / "research.md",
            ROOT / "references" / "celebrity_budget_unfriendly_framework.md",
            ROOT / ".github" / "PULL_REQUEST_TEMPLATE.md",
        ]
        single_language_paths.extend(
            ROOT / "docs" / "lang" / f"{stem}_{language}.md"
            for stem in ("README", "ROADMAP")
            for language in ("DE", "ES", "KO", "PT", "RU")
        )
        single_language_paths.extend(
            ROOT / ".github" / "ISSUE_TEMPLATE" / name
            for name in (
                "bug_report.md",
                "config.yml",
                "feature_request.md",
                "question.md",
            )
        )

        for path in single_language_paths:
            content = path.read_text(encoding="utf-8")
            self.assertIsNone(
                HAN_CHARACTER.search(content),
                f"Chinese copy remains in {path.relative_to(ROOT)}",
            )

        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = skill.split("---", 2)[1]
        chinese_skill = skill.split("# English Version", 1)[0]
        english_skill = skill.split("# English Version", 1)[1]
        self.assertIsNone(HAN_CHARACTER.search(frontmatter))
        self.assertIsNone(HAN_CHARACTER.search(english_skill))
        self.assertIn("本 Skill 支持中英文", chinese_skill)
        self.assertIsNotNone(HAN_CHARACTER.search(chinese_skill))

        for name in ("README_JA.md", "ROADMAP_JA.md"):
            content = (ROOT / "docs" / "lang" / name).read_text(encoding="utf-8")
            for stale_phrase in ("原同事", "留痕", "企業微信"):
                self.assertNotIn(stale_phrase, content, f"Chinese phrase in {name}")

    def test_code_uses_new_names_with_explicit_legacy_fallbacks(self) -> None:
        writer = (ROOT / "tools" / "skill_writer.py").read_text(encoding="utf-8")
        schema = (ROOT / "tools" / "skill_schema.py").read_text(encoding="utf-8")
        codex_installer = (ROOT / "tools" / "install_codex_skill.py").read_text(encoding="utf-8")
        generated_installer = (
            ROOT / "tools" / "install_generated_skill_common.py"
        ).read_text(encoding="utf-8")

        self.assertIn("DISTILLY_AUTO_INSTALL_CLAUDE", writer)
        self.assertIn("DOT_SKILL_AUTO_INSTALL_CLAUDE", writer)
        self.assertIn('engine.setdefault("name", "distilly")', schema)
        self.assertIn('generation.setdefault("engine", "distilly")', schema)
        self.assertIn('Path.home() / ".agents" / "skills" / "distilly"', codex_installer)
        self.assertIn('.distilly-install.json', generated_installer)

        for collector_name in (
            "feishu_auto_collector.py",
            "feishu_mcp_client.py",
            "dingtalk_auto_collector.py",
            "slack_auto_collector.py",
        ):
            collector = (ROOT / "tools" / collector_name).read_text(encoding="utf-8")
            self.assertIn('Path.home() / ".distilly"', collector)
            self.assertIn('Path.home() / ".colleague-skill"', collector)
            self.assertIn("CONFIG_PATH.chmod(0o600)", collector)


if __name__ == "__main__":
    unittest.main()
