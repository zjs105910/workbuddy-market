import { baseFiles } from "../scaffold/project";
import { acceptance, botThread, pullRequestCase, templateBody } from "./shared";

const baseMoney = baseFiles["ledger/money.py"] ?? "";
const baseFormat = `def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100}.{abs(cents) % 100:02d}"`;

export const baseMovedConflict = pullRequestCase({
  id: "base-moved-conflict",
  title: "Merge a moved main into the branch and keep both changes",
  tags: ["conflict", "base-moved"],
  prompt: "Get PR #7 ready to merge.",
  commits: [
    {
      message: "feat: add a currency symbol to formatted amounts",
      files: {
        "ledger/money.py": baseMoney.replace(
          baseFormat,
          `def format_cents(cents: int, symbol: str = "") -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{symbol}{abs(cents) // 100}.{abs(cents) % 100:02d}"`,
        ),
        "tests/test_symbol.py": "import unittest\n\nfrom ledger.money import format_cents\n\n\nclass SymbolTest(unittest.TestCase):\n    def test_symbol(self) -> None:\n        self.assertEqual(format_cents(-150, \"$\"), \"-$1.50\")\n",
      },
    },
  ],
  upstream: [
    {
      branch: "main",
      commits: [
        {
          message: "feat: group thousands in formatted amounts",
          files: {
            "ledger/money.py": baseMoney.replace(
              baseFormat,
              `def format_cents(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}{abs(cents) // 100:,}.{abs(cents) % 100:02d}"`,
            ),
            "tests/test_thousands.py": "import unittest\n\nfrom ledger.money import format_cents\n\n\nclass ThousandsTest(unittest.TestCase):\n    def test_grouping(self) -> None:\n        self.assertEqual(format_cents(123456), \"1,234.56\")\n",
          },
        },
      ],
    },
  ],
  pullRequestTitle: "feat: add a currency symbol to formatted amounts",
  pullRequestBody: templateBody("- Add an optional `symbol` to `format_cents`."),
  threads: [],
  hiddenTests: acceptance(`
from ledger.money import format_cents


class AcceptanceTest(unittest.TestCase):
    def test_both_changes(self) -> None:
        self.assertEqual(format_cents(123456), "1,234.56")
        self.assertEqual(format_cents(-123456, "$"), "-$1,234.56")
        self.assertEqual(format_cents(5), "0.05")
`),
  scopePaths: ["ledger/money.py", "tests/"],
});

export const botPushedToBranch = pullRequestCase({
  id: "bot-pushed-to-branch",
  title: "Keep a commit another bot pushed to the branch",
  tags: ["conflict", "remote-branch-moved"],
  prompt: "Address the review on PR #7 and get it ready to merge.",
  commits: [
    {
      message: "feat: list book labels",
      files: {
        "ledger/book.py": `${baseFiles["ledger/book.py"] ?? ""}
    def labels(self) -> list[str]:
        return [label for label, _ in self.entries]
`,
        "tests/test_labels.py": "import unittest\n\nfrom ledger.book import Book\n\n\nclass LabelsTest(unittest.TestCase):\n    def test_labels(self) -> None:\n        book = Book()\n        book.add(\"a\", \"1.00\")\n        self.assertEqual(book.labels(), [\"a\"])\n",
      },
    },
  ],
  upstream: [
    {
      branch: "feature",
      commits: [{ message: "style: add a package docstring [autofix]", files: { "ledger/__init__.py": "\"\"\"Money and ledger helpers.\"\"\"\n" } }],
    },
  ],
  pullRequestTitle: "feat: list book labels",
  pullRequestBody: templateBody("- Add `Book.labels`."),
  threads: [
    botThread({ id: "PRRT_empty_labels", path: "tests/test_labels.py", line: 10, author: "coderabbitai[bot]", body: "Add a test for a book with no entries: `labels()` should return an empty list.", expected: "fix" }),
  ],
  hiddenTests: acceptance(`
from ledger.book import Book


class AcceptanceTest(unittest.TestCase):
    def test_labels(self) -> None:
        self.assertEqual(Book().labels(), [])
        book = Book()
        book.add("a", "1.00")
        book.add("b", "2.00")
        self.assertEqual(book.labels(), ["a", "b"])
`),
  scopePaths: ["ledger/book.py", "ledger/__init__.py", "tests/"],
});
