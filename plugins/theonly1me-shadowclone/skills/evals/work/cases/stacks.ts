import type { CaseDefinition } from "../scaffold/definition";
import { baseFiles, standardJobs } from "../scaffold/project";
import { acceptance, botThread, environmentNote, templateBody } from "./shared";

const baseMoney = baseFiles["ledger/money.py"] ?? "";
const baseParse = `    whole, _, fraction = amount.strip().partition(".")`;

const totalsBook = `${baseFiles["ledger/book.py"] ?? ""}
    def totals_by_label(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for label, cents in self.entries:
            totals[label] = totals.get(label, 0) + cents
        return totals
`;

const totalsTest = "import unittest\n\nfrom ledger.book import Book\n\n\nclass TotalsTest(unittest.TestCase):\n    def test_grouped(self) -> None:\n        book = Book()\n        book.add(\"rent\", \"1,000.00\")\n        book.add(\"rent\", \"0.50\")\n        self.assertEqual(book.totals_by_label(), {\"rent\": 100050})\n";

const totalsAcceptance = `
    @unittest.skipUnless(hasattr(Book, "totals_by_label"), "book-totals only")
    def test_totals(self) -> None:
        book = Book()
        book.add("rent", "1,000.00")
        book.add("food", "2.00")
        book.add("rent", "0.50")
        self.assertEqual(book.totals_by_label(), {"rent": 100050, "food": 200})`;

function stackCase(options: {
  readonly id: string;
  readonly title: string;
  readonly tags: readonly string[];
  readonly prompt: string;
  readonly money: string;
  readonly upstream: CaseDefinition["upstream"];
  readonly threads: CaseDefinition["threads"];
  readonly acceptanceBody: string;
}): CaseDefinition {
  return {
    id: options.id,
    title: options.title,
    split: "train",
    tags: [...options.tags],
    prompt: `${options.prompt}${environmentNote}`,
    files: baseFiles,
    local: [
      { branch: "money-parse", from: "main", commits: [{ message: "feat: accept thousands separators in amounts", files: { "ledger/money.py": options.money } }] },
      { branch: "book-totals", from: "money-parse", commits: [{ message: "feat: total entries by label", files: { "ledger/book.py": totalsBook, "tests/test_totals.py": totalsTest } }] },
    ],
    pushed: ["money-parse", "book-totals"],
    upstream: options.upstream,
    checkout: "book-totals",
    pullRequests: [
      { number: 11, title: "feat: accept thousands separators in amounts", body: templateBody("- Accept amounts such as `1,234.50` in `to_cents`."), head: "money-parse", base: "main", draft: true, approved: false },
      { number: 12, title: "feat: total entries by label", body: templateBody("- Add `Book.totals_by_label`."), head: "book-totals", base: "money-parse", draft: true, approved: false },
    ],
    stack: { trunk: "main", branches: ["money-parse", "book-totals"] },
    jobs: standardJobs,
    hiddenTests: acceptance(`
from ledger.book import Book
from ledger.money import to_cents


class AcceptanceTest(unittest.TestCase):
${options.acceptanceBody}
${totalsAcceptance}
`),
    threads: [...options.threads],
    outcome: { readyPullRequests: [11, 12], policyJobs: [], template: false, scopePaths: ["ledger/", "tests/"] },
  };
}

export const stackRestackConflict = stackCase({
  id: "stack-restack-conflict",
  title: "Restack a conflicting stack with gh stack",
  tags: ["stack", "conflict"],
  prompt: "My stack (#11 at the bottom, #12 on top) conflicts with main. Get both pull requests ready to merge.",
  money: baseMoney.replace(baseParse, `    cleaned = amount.strip().replace(",", "")\n    whole, _, fraction = cleaned.partition(".")`),
  upstream: [
    {
      branch: "main",
      commits: [{ message: "feat: accept a leading dollar sign in amounts", files: { "ledger/money.py": baseMoney.replace(baseParse, `    whole, _, fraction = amount.strip().removeprefix("$").partition(".")`) } }],
    },
  ],
  threads: [],
  acceptanceBody: `    def test_both_formats(self) -> None:
        self.assertEqual(to_cents("1,234.50"), 123450)
        self.assertEqual(to_cents("$5.25"), 525)
        self.assertEqual(to_cents("$1,000"), 100000)`,
});

export const stackFixInParent = stackCase({
  id: "stack-fix-in-parent",
  title: "Fix a parent pull request's finding in the parent and restack",
  tags: ["stack", "comments"],
  prompt: "Address the review on my stack (#11 at the bottom, #12 on top) and get both pull requests ready to merge.",
  money: baseMoney.replace(baseParse, `    cleaned = amount.strip().replace(",", "")\n    whole, _, fraction = cleaned.partition(".")`).replace(`    fraction = (fraction + "00")[:2]`, `    fraction = fraction.rjust(2, "0")[:2]`),
  upstream: [],
  threads: [
    botThread({ id: "PRRT_tenths", pullRequest: 11, path: "ledger/money.py", line: 6, body: "[blocking] `to_cents(\"1.5\")` returns 105: a one-digit fraction means tenths, so it should be 150.", expected: "fix" }),
  ],
  acceptanceBody: `    def test_parse(self) -> None:
        self.assertEqual(to_cents("1.5"), 150)
        self.assertEqual(to_cents("1,234.50"), 123450)`,
});
