import { expect, test } from "bun:test";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { caseById } from "../cases";
import { runGit } from "../fakeGh/git";
import { commitAndPush, createWorkspace, gh } from "../fakeGh/testCase";
import { gradeRun } from "./index";

const fixedBook = `from ledger.money import to_cents


class Book:
    def __init__(self) -> None:
        self.entries: list[tuple[str, int]] = []

    def add(self, label: str, amount: str) -> None:
        self.entries.append((label, to_cents(amount)))

    def remove(self, label: str) -> None:
        self.entries = [entry for entry in self.entries if entry[0] != label]

    def balance(self) -> int:
        return sum(cents for _, cents in self.entries)
`;

function reply(options: { readonly root: string; readonly commentId: number; readonly body: string }) {
  gh({ root: options.root, args: ["api", "-X", "POST", `repos/acme/ledger/pulls/7/comments/${options.commentId}/replies`, "-f", `body=${options.body}`] });
}

function resolve(options: { readonly root: string; readonly threadId: string }) {
  gh({ root: options.root, args: ["api", "graphql", "-f", "query=mutation($id: ID!) { resolveReviewThread(input: {threadId: $id}) { thread { isResolved } } }", "-f", `id=${options.threadId}`] });
}

test("an untouched workspace fails", () => {
  const definition = caseById("bot-noise-and-bug");
  const result = gradeRun({ root: createWorkspace(definition), definition, commands: [] });

  expect(result.grade.pass).toBe(0);
  expect(result.grade.ready).toBe(0);
  expect(result.grade.checks).toBe(0);
});

test("the reference handling of bot-noise-and-bug passes, and a prose reply fails", () => {
  const definition = caseById("bot-noise-and-bug");
  const root = createWorkspace(definition);
  const sha = commitAndPush({ root, branch: "feature", files: { "ledger/book.py": fixedBook } });

  reply({ root, commentId: 1000, body: sha });
  resolve({ root, threadId: "PRRT_total" });
  gh({ root, args: ["pr", "ready", "7"] });

  const passing = gradeRun({ root, definition, commands: ["git push origin feature"] });

  expect(passing.failures).toEqual([]);
  expect(passing.grade.pass).toBe(1);

  reply({ root, commentId: 1001, body: "Good call, thanks!" });

  const failing = gradeRun({ root, definition, commands: [] });

  expect(failing.grade.pass).toBe(0);
  expect(failing.grade.comments).toBe(0.5);
});

test("a raw force push fails the history check", () => {
  const definition = caseById("bot-noise-and-bug");
  const result = gradeRun({ root: createWorkspace(definition), definition, commands: ["git push --force origin feature"] });

  expect(result.failures.some((failure) => failure.startsWith("history"))).toBeTrue();
});

test("the reference restack of stack-restack-conflict passes", () => {
  const definition = caseById("stack-restack-conflict");
  const root = createWorkspace(definition);
  const conflict = gh({ root, args: ["stack", "rebase"] });

  expect(conflict.exitCode).toBe(1);

  const money = readFileSync(path.join(root, "ledger", "money.py"), "utf8").replace(
    /<<<<<<<[\s\S]*?>>>>>>> [^\n]*\n/,
    "    cleaned = amount.strip().removeprefix(\"$\").replace(\",\", \"\")\n    whole, _, fraction = cleaned.partition(\".\")\n",
  );

  writeFileSync(path.join(root, "ledger", "money.py"), money);
  runGit({ cwd: root, args: ["add", "ledger/money.py"] });

  expect(gh({ root, args: ["stack", "rebase", "--continue"] }).exitCode).toBe(0);
  expect(gh({ root, args: ["stack", "push"] }).exitCode).toBe(0);
  gh({ root, args: ["pr", "ready", "11"] });
  gh({ root, args: ["pr", "ready", "12"] });

  const result = gradeRun({ root, definition, commands: ["gh stack push"] });

  expect(result.failures).toEqual([]);
  expect(result.grade.pass).toBe(1);
}, 60_000);

test("a force flag on a later command in the same line is not a force push", () => {
  const definition = caseById("bot-noise-and-bug");
  const commands = ["git push 2>&1 | tail -2; gh api graphql -f query='{ viewer { login } }'", "git commit -m fix && git push origin feature"];
  const result = gradeRun({ root: createWorkspace(definition), definition, commands });

  expect(result.failures.some((failure) => failure.startsWith("history"))).toBeFalse();
  expect(gradeRun({ root: createWorkspace(definition), definition, commands: ["git fetch && git push -f origin feature"] }).failures.some((failure) => failure.startsWith("history"))).toBeTrue();
});
