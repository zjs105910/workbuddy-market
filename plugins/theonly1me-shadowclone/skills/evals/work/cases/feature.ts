import type { CaseDefinition } from "../scaffold/definition";
import { baseFiles, standardJobs } from "../scaffold/project";
import { acceptance, botThread, environmentNote } from "./shared";

export const newFeatureTemplate: CaseDefinition = {
  id: "new-feature-template",
  title: "Implement an issue from scratch to a ready pull request",
  split: "train",
  tags: ["new-feature", "template", "late-review"],
  prompt: `Implement issue #31 and take it to a pull request that is ready to merge.

Issue #31: Add \`parse_amounts(text)\` to \`ledger/money.py\`. It takes a comma-separated string such as "1.50, -2, 3.05" and returns the total in cents (255 for that example). Empty input returns 0. Add tests.${environmentNote}`,
  files: baseFiles,
  local: [],
  pushed: [],
  upstream: [],
  checkout: "main",
  pullRequests: [],
  stack: null,
  jobs: standardJobs,
  hiddenTests: acceptance(`
from ledger.money import parse_amounts


class AcceptanceTest(unittest.TestCase):
    def test_example(self) -> None:
        self.assertEqual(parse_amounts("1.50, -2, 3.05"), 255)

    def test_empty(self) -> None:
        self.assertEqual(parse_amounts(""), 0)

    def test_blank_items(self) -> None:
        self.assertEqual(parse_amounts("1, ,2"), 300)
`),
  threads: [
    botThread({
      id: "PRRT_blank",
      pullRequest: 42,
      path: "ledger/money.py",
      line: 12,
      release: "pr-created",
      body: "[suggestion] `parse_amounts(\"1, ,2\")` raises `ValueError` on the blank item between the commas. Skip blank items so the total is 300.",
      expected: "fix",
    }),
  ],
  outcome: { readyPullRequests: [42], policyJobs: [], template: true, scopePaths: ["ledger/", "tests/"] },
};
