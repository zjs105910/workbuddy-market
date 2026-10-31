import { mkdtempSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { buildWorkspace } from "../scaffold/build";
import type { CaseDefinition } from "../scaffold/definition";
import { baseFiles, standardJobs } from "../scaffold/project";
import { runGit } from "./git";
import { runFakeGh } from "./index";
import { readState, workspaceFor } from "./state";

export const acceptanceTest = {
  "ci_acceptance/__init__.py": "",
  "ci_acceptance/test_acceptance.py": "import unittest\n\nfrom ledger.money import format_cents\n\n\nclass AcceptanceTest(unittest.TestCase):\n    def test_zero(self) -> None:\n        self.assertEqual(format_cents(0), \"0.00\")\n",
};

export function sampleCase(overrides: Partial<CaseDefinition>): CaseDefinition {
  return {
    id: "sample",
    title: "Sample",
    split: "train",
    tags: ["sample"],
    prompt: "Get pull request 7 ready for review.",
    files: baseFiles,
    local: [{ branch: "feature", from: "main", commits: [{ message: "feat: add total", files: { "ledger/total.py": "def total(values: list[int]) -> int:\n    return sum(values)\n" } }] }],
    pushed: ["feature"],
    upstream: [],
    checkout: "feature",
    pullRequests: [{ number: 7, title: "Add total", body: "## Summary\n\n- Add total.\n", head: "feature", base: "main", draft: true, approved: false }],
    stack: null,
    jobs: standardJobs,
    hiddenTests: acceptanceTest,
    threads: [
      { id: "PRRT_bot", pullRequest: 7, path: "ledger/total.py", line: 1, author: "coderabbitai[bot]", bot: true, body: "Handle an empty list.", release: "initial", expected: "fix" },
      { id: "PRRT_late", pullRequest: 7, path: "ledger/total.py", line: 2, author: "cursor[bot]", bot: true, body: "Possible overflow.", release: "head-changed", expected: "decline" },
    ],
    outcome: { readyPullRequests: [7], policyJobs: [], template: false, scopePaths: ["ledger/"] },
    ...overrides,
  };
}

export function createWorkspace(definition: CaseDefinition): string {
  const root = mkdtempSync(path.join(os.tmpdir(), "fake-gh-test-"));

  buildWorkspace({ root, definition });

  return root;
}

export function gh(options: { readonly root: string; readonly args: readonly string[] }) {
  return runFakeGh({ root: options.root, cwd: options.root, args: options.args });
}

export function commitAndPush(options: {
  readonly root: string;
  readonly files: Readonly<Record<string, string>>;
  readonly branch: string;
}): string {
  for (const [relative, content] of Object.entries(options.files)) {
    writeFileSync(path.join(options.root, relative), content);
  }

  runGit({ cwd: options.root, args: ["add", "--all"] });
  runGit({ cwd: options.root, args: ["commit", "--quiet", "-m", "fix: handle review"] });
  runGit({ cwd: options.root, args: ["push", "--quiet", "origin", options.branch] });

  return runGit({ cwd: options.root, args: ["rev-parse", "HEAD"] }).stdout.trim();
}

export function stateOf(root: string) {
  return readState(workspaceFor(root));
}
