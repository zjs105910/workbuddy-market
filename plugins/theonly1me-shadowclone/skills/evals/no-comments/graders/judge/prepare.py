from pathlib import Path

from graders.comments import strip_comments
from harness.config import SEED_REPO


def changed_source_paths(final_directory: Path) -> list[Path]:
    paths = []
    for path in sorted((final_directory / "ledger").rglob("*.py")):
        relative = path.relative_to(final_directory)
        seed_path = SEED_REPO / relative
        if not seed_path.exists() or seed_path.read_text() != path.read_text():
            paths.append(path)
    return paths


def render_implementation(final_directory: Path) -> str:
    sections = []
    for path in changed_source_paths(final_directory):
        relative = path.relative_to(final_directory)
        sections.append(f"### {relative}\n```python\n{strip_comments(path.read_text())}```")
    return "\n\n".join(sections)
