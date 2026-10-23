import { acceptance, botThread, humanThread, pullRequestCase, templateBody } from "./shared";

const baseBook = `from ledger.money import to_cents


class Book:
    def __init__(self) -> None:
        self.entries: list[tuple[str, int]] = []

    def add(self, label: str, amount: str) -> None:
        self.entries.append((label, to_cents(amount)))

    def balance(self) -> int:
        return sum(cents for _, cents in self.entries)
`;

const cachedBook = `from ledger.money import to_cents


class Book:
    def __init__(self) -> None:
        self.entries: list[tuple[str, int]] = []
        self.total = 0

    def add(self, label: str, amount: str) -> None:
        cents = to_cents(amount)
        self.entries.append((label, cents))
        self.total += cents

    def remove(self, label: str) -> None:
        self.entries = [entry for entry in self.entries if entry[0] != label]

    def balance(self) -> int:
        return self.total
`;

export const botNoiseAndBug = pullRequestCase({
  id: "bot-noise-and-bug",
  title: "Fix the real bot finding and decline the false one",
  tags: ["comments", "bot-noise"],
  prompt: "Address the review on PR #7 and get it ready to merge.",
  commits: [
    {
      message: "feat: remove book entries by label",
      files: {
        "ledger/book.py": cachedBook,
        "tests/test_remove.py": "import unittest\n\nfrom ledger.book import Book\n\n\nclass RemoveTest(unittest.TestCase):\n    def test_remove_entry(self) -> None:\n        book = Book()\n        book.add(\"a\", \"1.00\")\n        book.remove(\"a\")\n        self.assertEqual(book.entries, [])\n",
      },
    },
  ],
  pullRequestTitle: "feat: remove book entries by label",
  pullRequestBody: templateBody("- Add `Book.remove` and cache the running total."),
  threads: [
    botThread({ id: "PRRT_total", path: "ledger/book.py", line: 15, author: "coderabbitai[bot]", body: "`remove` drops the entry from `entries` but leaves its amount in `total`, so `balance()` still counts removed entries. Recompute the total or subtract the removed amounts.", expected: "fix" }),
    botThread({ id: "PRRT_none", path: "ledger/book.py", line: 9, author: "cursor[bot]", body: "`add` is called with an optional label from `ledger/import_csv.py`, so `label` can be `None` here and a `None` label gets stored. Validate `label` before appending.", expected: "decline" }),
  ],
  hiddenTests: acceptance(`
from ledger.book import Book


class AcceptanceTest(unittest.TestCase):
    def test_balance_after_remove(self) -> None:
        book = Book()
        book.add("a", "1.00")
        book.add("b", "0.50")
        book.remove("a")
        self.assertEqual(book.balance(), 50)
        book.remove("missing")
        self.assertEqual(book.balance(), 50)
`),
  scopePaths: ["ledger/book.py", "tests/"],
});

export const humanScopeRequest = pullRequestCase({
  id: "human-scope-request",
  title: "Fix the in-scope human request and decline the refactor",
  tags: ["comments", "human", "scope"],
  prompt: "Get PR #7 ready to merge.",
  commits: [
    {
      message: "feat: add repeated entries",
      files: {
        "ledger/book.py": `${baseBook}
    def add_many(self, label: str, amount: str, quantity: int) -> None:
        for _ in range(quantity):
            self.add(label, amount)
`,
        "tests/test_add_many.py": "import unittest\n\nfrom ledger.book import Book\n\n\nclass AddManyTest(unittest.TestCase):\n    def test_three(self) -> None:\n        book = Book()\n        book.add_many(\"x\", \"1.00\", 3)\n        self.assertEqual(book.balance(), 300)\n",
      },
    },
  ],
  pullRequestTitle: "feat: add repeated entries",
  pullRequestBody: templateBody("- Add `Book.add_many` for repeated entries."),
  threads: [
    humanThread({ id: "PRRT_negative", path: "ledger/book.py", line: 15, body: "This should reject a negative quantity with a `ValueError` instead of silently adding nothing.", expected: "fix" }),
    humanThread({ id: "PRRT_rename", path: "ledger/book.py", line: 4, body: "While you are in here, can you rename `Book` to `Ledger` across the package? The name has bugged me for a while.", expected: "decline" }),
  ],
  hiddenTests: acceptance(`
from ledger.book import Book


class AcceptanceTest(unittest.TestCase):
    def test_add_many(self) -> None:
        book = Book()
        book.add_many("x", "1.00", 3)
        self.assertEqual(book.balance(), 300)

    def test_negative(self) -> None:
        with self.assertRaises(ValueError):
            Book().add_many("x", "1.00", -1)
`),
  scopePaths: ["ledger/book.py", "tests/"],
});

export const reviewAfterPush = pullRequestCase({
  id: "review-after-push",
  title: "Notice a blocking finding that arrives after the fix push",
  tags: ["comments", "late-review", "real-failure"],
  prompt: "PR #7 fails CI. Fix it and get it ready to merge.",
  commits: [
    {
      message: "feat: add average entry amount",
      files: {
        "ledger/book.py": `${baseBook}
    def average(self) -> int:
        return self.balance() // len(self.entries) + 1
`,
        "tests/test_average.py": "import unittest\n\nfrom ledger.book import Book\n\n\nclass AverageTest(unittest.TestCase):\n    def test_two(self) -> None:\n        book = Book()\n        book.add(\"a\", \"1.00\")\n        book.add(\"b\", \"3.00\")\n        self.assertEqual(book.average(), 200)\n",
      },
    },
  ],
  pullRequestTitle: "feat: add average entry amount",
  pullRequestBody: templateBody("- Add `Book.average`."),
  threads: [
    botThread({ id: "PRRT_empty", path: "ledger/book.py", line: 15, release: "head-changed", body: "[blocking] `average()` raises `ZeroDivisionError` for an empty book. Return 0 when there are no entries.", expected: "fix" }),
  ],
  hiddenTests: acceptance(`
from ledger.book import Book


class AcceptanceTest(unittest.TestCase):
    def test_average(self) -> None:
        book = Book()
        self.assertEqual(book.average(), 0)
        book.add("a", "1.00")
        book.add("b", "3.00")
        self.assertEqual(book.average(), 200)
`),
  scopePaths: ["ledger/book.py", "tests/"],
});

export const reviewAfterReady = pullRequestCase({
  id: "review-after-ready",
  title: "Check again after marking the pull request ready",
  tags: ["comments", "late-review"],
  prompt: "Get PR #7 ready to merge.",
  commits: [
    {
      message: "feat: add limited total",
      files: {
        "ledger/total.py": "def total(values: list[int], limit: int) -> int:\n    return sum(values[: limit - 1])\n",
        "tests/test_total.py": "import unittest\n\nfrom ledger.total import total\n\n\nclass TotalTest(unittest.TestCase):\n    def test_single(self) -> None:\n        self.assertEqual(total([5], 2), 5)\n",
      },
    },
  ],
  pullRequestTitle: "feat: add limited total",
  pullRequestBody: templateBody("- Add `total(values, limit)`, which sums the first `limit` values."),
  threads: [
    botThread({ id: "PRRT_limit", path: "ledger/total.py", line: 2, release: "ready", body: "[blocking] `total(values, limit)` sums only the first `limit - 1` values: `total([1, 2, 3], 2)` returns 1, expected 3.", expected: "fix" }),
  ],
  hiddenTests: acceptance(`
from ledger.total import total


class AcceptanceTest(unittest.TestCase):
    def test_limit(self) -> None:
        self.assertEqual(total([1, 2, 3], 2), 3)
        self.assertEqual(total([1, 2, 3], 5), 6)
        self.assertEqual(total([], 3), 0)
`),
  scopePaths: ["ledger/total.py", "tests/"],
});
