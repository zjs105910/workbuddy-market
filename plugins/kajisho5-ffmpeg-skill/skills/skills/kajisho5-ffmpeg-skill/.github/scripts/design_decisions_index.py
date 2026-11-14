"""The contents list at the top of docs/design-decisions.md, built from its `## ` headings.

The file is 170 KB of decisions added release by release, so a reader looking for "what was
decided about colour" or "what changed in 2.10.9" needs the list, and a hand-kept list drifts.
`tests/test_contract.py` fails when the list in the file is not what this builds; run

    python3 .github/scripts/design_decisions_index.py --write

to regenerate it. release.yml also calls `release_headings()` so a section written as
`## Unreleased — ...` is renamed to the version that shipped it, the way CHANGELOG.md's
`## Unreleased` section is.
"""
import re
import sys
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "docs" / "design-decisions.md"
START, END = "<!-- contents:start -->", "<!-- contents:end -->"
# Topic sections come first in the file; from the first of these on, sections are dated.
FIRST_DATED = "Decided for 2.0"


def slug(heading: str, seen: dict) -> str:
    """GitHub's anchor for a heading: lower-cased, punctuation dropped, spaces to hyphens,
    and -1, -2 ... on a repeat."""
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")
    n = seen.get(s, 0)
    seen[s] = n + 1
    return s if n == 0 else f"{s}-{n}"


def build(text: str) -> str:
    headings = re.findall(r"^## (.+)$", text, re.M)
    seen: dict = {}
    topic, dated, in_dated = [], [], False
    for h in headings:
        in_dated = in_dated or h.startswith(FIRST_DATED)
        (dated if in_dated else topic).append(f"- [{h}](#{slug(h, seen)})")
    return (f"{START}\n**By topic:**\n\n" + "\n".join(topic)
            + "\n\n**By release, review or plan** (in the order they were added):\n\n" + "\n".join(dated) + f"\n{END}")


def apply(text: str) -> str:
    block = build(text)
    if START in text:
        return re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _: block, text, flags=re.S)
    first = re.search(r"^## ", text, re.M)
    return text[:first.start()] + block + "\n\n" + text[first.start():]


def release_headings(text: str, version: str) -> str:
    """`## Unreleased — topic` becomes `## <version> — topic`, and the contents list follows."""
    return apply(re.sub(r"^## Unreleased — ", f"## {version} — ", text, flags=re.M))


if __name__ == "__main__":
    text = PATH.read_text(encoding="utf-8")
    new = apply(text)
    if "--write" in sys.argv:
        PATH.write_text(new, encoding="utf-8")
    elif new != text:
        sys.exit("docs/design-decisions.md: the contents list is stale; run with --write")
