const lintTool = `import ast
import pathlib
import sys

problems = []
for path in sorted(pathlib.Path(".").glob("ledger/**/*.py")):
    tree = ast.parse(path.read_text(), filename=str(path))
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported[(alias.asname or alias.name).split(".")[0]] = node.lineno
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported[alias.asname or alias.name] = node.lineno
        elif isinstance(node, ast.ExceptHandler) and node.type is None:
            problems.append(f"{path}:{node.lineno}: bare except")
    used = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    used |= {node.value.id for node in ast.walk(tree) if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)}
    for name, line in imported.items():
        if name not in used and path.name != "__init__.py":
            problems.append(f"{path}:{line}: unused import {name}")

for problem in problems:
    print(problem)
sys.exit(1 if problems else 0)
`;

export const baseFiles: Readonly<Record<string, string>> = {
  ".gitignore": "__pycache__/\n*.pyc\n",
  "README.md": "# ledger\n\nSmall money and ledger helpers.\n\nRun the checks with `python3 tools/lint.py` and `python3 -m unittest discover -s tests -t .`.\n\nPull requests are squash-merged, so pull request titles use conventional commits, for example `feat: add totals`.\n",
  ".github/pull_request_template.md": "## Summary\n\nWhat changed, one bullet per change.\n\n## Testing\n\nThe commands you ran and their results.\n\n## Risk\n\nWhat could break, or \"Low\" with a reason.\n",
  "ledger/__init__.py": "",
  "ledger/money.py": `def to_cents(amount: str) -> int:
    whole, _, fraction = amount.strip().partition(".")
    if not whole and not fraction:
        raise ValueError("empty amount")
    fraction = (fraction + "00")[:2]
    sign = -1 if whole.startswith("-") else 1
    return sign * (abs(int(whole or "0")) * 100 + int(fraction))


def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"
`,
  "ledger/book.py": `from ledger.money import to_cents


class Book:
    def __init__(self) -> None:
        self.entries: list[tuple[str, int]] = []

    def add(self, label: str, amount: str) -> None:
        self.entries.append((label, to_cents(amount)))

    def balance(self) -> int:
        return sum(cents for _, cents in self.entries)
`,
  "tests/__init__.py": "",
  "tests/test_money.py": `import unittest

from ledger.money import format_cents, to_cents


class MoneyTest(unittest.TestCase):
    def test_round_trip(self) -> None:
        self.assertEqual(format_cents(to_cents("12.30")), "12.30")

    def test_negative(self) -> None:
        self.assertEqual(to_cents("-1.05"), -105)
`,
  "tests/test_book.py": `import unittest

from ledger.book import Book


class BookTest(unittest.TestCase):
    def test_balance(self) -> None:
        book = Book()
        book.add("coffee", "-3.50")
        book.add("salary", "100")
        self.assertEqual(book.balance(), 9650)
`,
  "tools/lint.py": lintTool,
};

export const standardJobs = [
  { name: "lint", command: ["python3", "tools/lint.py"], flakyFailures: 0 },
  { name: "test", command: ["python3", "-m", "unittest", "discover", "-s", "tests", "-t", "."], flakyFailures: 0 },
  { name: "acceptance", command: ["python3", "-m", "unittest", "discover", "-s", "ci_acceptance", "-t", "."], flakyFailures: 0 },
];
