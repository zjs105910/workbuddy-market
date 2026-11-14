"""Guard: every SKILL.md frontmatter must be valid, loadable YAML.

Regression test for the v3.1.2 -> v3.1.3 break: an unquoted description that
contained ': ' (colon followed by space) turned the frontmatter into an invalid
YAML mapping ("mapping values are not allowed here"), which breaks skill loading
and the model-triggering description field. The version-parity check is a regex
and did not catch it, so this validates the frontmatter as actual YAML.

clawhub-upload/SKILL.md is gitignored and may be absent on a fresh clone; glob
simply does not find it then, which is fine.
"""
import glob
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _skill_md_files():
    out = []
    for p in glob.glob(str(REPO_ROOT / "**" / "SKILL.md"), recursive=True):
        parts = Path(p).parts
        if ".git" in parts or "node_modules" in parts:
            continue
        out.append(Path(p))
    return out


def _frontmatter(text):
    if not text.startswith("---"):
        return None
    segments = text.split("---", 2)
    if len(segments) < 3:
        return None
    return segments[1]


def _description_line(frontmatter):
    for line in frontmatter.splitlines():
        if line.startswith("description:"):
            return line
    return None


class SkillFrontmatterTests(unittest.TestCase):
    def test_files_found(self):
        self.assertTrue(_skill_md_files(), "no SKILL.md files discovered")

    def test_every_skill_has_frontmatter_and_description(self):
        for f in _skill_md_files():
            fm = _frontmatter(f.read_text(encoding="utf-8"))
            self.assertIsNotNone(fm, f"{f} has no '---' frontmatter block")
            self.assertIsNotNone(
                _description_line(fm), f"{f} frontmatter has no description:"
            )

    def test_unquoted_description_has_no_colon_space(self):
        # Dependency-free guard for the exact v3.1.2 break.
        for f in _skill_md_files():
            fm = _frontmatter(f.read_text(encoding="utf-8"))
            if fm is None:
                continue
            line = _description_line(fm)
            if line is None:
                continue
            value = line[len("description:"):].strip()
            if value[:1] in ('"', "'"):
                continue  # quoted scalars may safely contain colons
            self.assertNotIn(
                ": ",
                value,
                f"{f}: unquoted description contains ': ', which YAML parses as a "
                f"mapping and breaks frontmatter loading. Quote the value.",
            )

    def test_frontmatter_parses_as_yaml(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        for f in _skill_md_files():
            fm = _frontmatter(f.read_text(encoding="utf-8"))
            if fm is None:
                continue
            try:
                data = yaml.safe_load(fm)
            except Exception as exc:  # noqa: BLE001
                self.fail(f"{f}: frontmatter is not valid YAML: {exc}")
            self.assertIsInstance(data, dict, f"{f}: frontmatter is not a mapping")
            self.assertIsInstance(
                data.get("description"),
                str,
                f"{f}: description missing or not a string after YAML parse",
            )
            self.assertTrue(
                data["description"].strip(), f"{f}: description is empty"
            )


if __name__ == "__main__":
    unittest.main()
