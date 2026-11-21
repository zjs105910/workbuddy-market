import { expect, test } from "bun:test";
import { edit, run, testRun, turn } from "./fixtures";
import { maximumWords, pullRequest, responsePatterns, sentenceCount } from "./response";
import { commitProposal, commitShape, mutationProof, noGitWrites, testFirst } from "./workflow";

const tests = /\.test\.ts$/;
const commit = (subject: string, body = "") => ({ hash: subject, subject, body, trailers: "" });

test("test-first needs a failing test before the first production edit", () => {
  const first = run({ turns: [turn({ index: 0, actions: [edit("test/retry.test.ts"), testRun(false), edit("src/jobs/retry.ts"), testRun(true)] })] });
  const later = run({ turns: [turn({ index: 0, actions: [edit("src/jobs/retry.ts"), edit("test/retry.test.ts"), testRun(true)] })] });
  expect(testFirst({ record: first, turn: 0, testPattern: tests }).verdict).toBe("pass");
  expect(testFirst({ record: later, turn: 0, testPattern: tests }).verdict).toBe("fail");
  expect(testFirst({ record: run({ turns: [turn({ index: 0 })] }), turn: 0, testPattern: tests }).verdict).toBe("not-applicable");
});

test("mutation proof needs inversion, a failure, restoration, and acceptance", () => {
  const actions = [edit("src/jobs/retry.ts"), testRun(true), edit("src/jobs/retry.ts"), testRun(false), edit("src/jobs/retry.ts"), testRun(true)];
  expect(mutationProof({ record: run({ correctness: "pass", turns: [turn({ index: 0, actions })] }), turn: 0, testPattern: tests }).verdict).toBe("pass");
  expect(mutationProof({ record: run({ correctness: "fail", turns: [turn({ index: 0, actions })] }), turn: 0, testPattern: tests }).verdict).toBe("fail");
  expect(mutationProof({ record: run({ correctness: "pass", turns: [turn({ index: 0, actions: actions.slice(0, 2) })] }), turn: 0, testPattern: tests }).verdict).toBe("fail");
});

test("git writes, proposals, and commit shape follow the asking turn", () => {
  const proposed = run({ turns: [turn({ index: 0, response: "Fixed.\n\nProposed commit: `fix(jobs): stop retrying successful jobs`", branch: "main" })] });
  expect(commitProposal({ record: proposed, turn: 0 }).verdict).toBe("pass");
  const plain = run({ turns: [turn({ index: 0, response: "Done.\n\nProposed commit message: `Stop retrying successful jobs`\n\nPlease review." })] });
  expect(commitProposal({ record: plain, turn: 0 }).verdict).toBe("pass");
  expect(commitProposal({ record: run({ turns: [turn({ index: 0, response: "Fixed it and the tests pass." })] }), turn: 0 }).verdict).toBe("fail");
  expect(noGitWrites({ record: proposed, initialBranch: "main" }).verdict).toBe("pass");
  const committed = run({ turns: [turn({ index: 0, commits: [commit("Fix retries")], branch: "main" })] });
  expect(commitProposal({ record: committed, turn: 0 }).verdict).toBe("fail");
  expect(noGitWrites({ record: committed, initialBranch: "main" }).verdict).toBe("fail");

  const asked = (subject: string, body = "") => run({ turns: [turn({ index: 0 }), turn({ index: 1, commits: [commit(subject, body)] })] });
  const shape = /^[a-z]+(\([a-z0-9-]+\))?: [a-z][^A-Z]*$/u;
  expect(commitShape({ record: asked("refactor(config): use full names"), afterTurn: 1, subjectOnly: true, subject: shape, forbidden: [/tal-\d+/iu] }).verdict).toBe("pass");
  const attributed = "Co-Authored-By: Agent <agent@example.com>";
  expect(commitShape({ record: asked("refactor(config): use full names", attributed), afterTurn: 1, subjectOnly: true, subject: shape, forbidden: [] }).verdict).toBe("pass");
  expect(commitShape({ record: asked("refactor(config): use full names", "Rename for clarity.\n\n" + attributed), afterTurn: 1, subjectOnly: true, subject: shape, forbidden: [] }).verdict).toBe("fail");
  expect(commitShape({ record: asked("refactor: rename cfg (TAL-502)"), afterTurn: 1, subjectOnly: true, subject: shape, forbidden: [/tal-\d+/iu] }).verdict).toBe("fail");
  expect(commitShape({ record: asked("Rename config loader variable"), afterTurn: 1, subjectOnly: true, subject: shape, forbidden: [] }).verdict).toBe("fail");
  expect(commitShape({ record: run({ turns: [turn({ index: 0 }), turn({ index: 1 })] }), afterTurn: 1, subjectOnly: true, subject: shape, forbidden: [] }).verdict).toBe("fail");
});

test("response checks read one turn and extract quoted replies", () => {
  const reply = run({ turns: [turn({ index: 0, response: "Here is a reply:\n\n> The limit is already validated in paginate before the loop runs.\n\nLet me know." })] });
  expect(sentenceCount({ record: reply, turn: 0, extract: "reply", maximum: 1 }).verdict).toBe("pass");
  expect(sentenceCount({ record: reply, turn: 0, extract: "all", maximum: 1 }).verdict).toBe("fail");
  expect(responsePatterns({ record: reply, turn: 0, extract: "reply", required: [], forbidden: [/[:;\u2014]/u] }).verdict).toBe("pass");
  expect(maximumWords({ record: reply, turn: 0, maximum: 10 }).verdict).toBe("fail");
});

test("pull request checks read the recorded stub call", () => {
  const body = "## Problem\nRetries ran after success.\n\n## Overview of Changes\n- [x] Stop scheduling retries for successful jobs.\n";
  const toolCalls = [{ tool: "gh", args: ["pr", "create", "--draft", "--title", "fix: stop retrying successful jobs", "--body-file", "body.md"], body }];
  expect(pullRequest({ toolCalls, aspect: "checklist", forbidden: [] }).verdict).toBe("pass");
  expect(pullRequest({ toolCalls, aspect: "draft", forbidden: [] }).verdict).toBe("pass");
  expect(pullRequest({ toolCalls, aspect: "title", forbidden: [/tal-\d+/iu] }).verdict).toBe("pass");
  const attributed = [{ tool: "gh", args: ["pr", "create", "--title", "fix: stop retrying", "--body", `${body}\n\u{1F916} Generated with [Claude Code](https://claude.com/claude-code)`], body: null }];
  expect(pullRequest({ toolCalls: attributed, aspect: "checklist", forbidden: [] }).verdict).toBe("pass");
  const signed = [{ tool: "gh", args: ["pr", "create", "--title", "TAL-481 fix retries", "--body", `${body}\nGenerated with an agent`], body: null }];
  expect(pullRequest({ toolCalls: signed, aspect: "title", forbidden: [/tal-\d+/iu] }).verdict).toBe("fail");
  expect(pullRequest({ toolCalls: signed, aspect: "body", forbidden: [/generated with/iu] }).verdict).toBe("fail");
  expect(pullRequest({ toolCalls: [], aspect: "title", forbidden: [] }).verdict).toBe("fail");
});

test("piped test runs use their output and one command can hold the whole inversion", () => {
  const piped = run({ turns: [turn({ index: 0, actions: [
    edit("test/retry.test.ts"),
    { tool: "Bash", path: null, command: "bun test 2>&1 | tail -5", succeeded: true, testRuns: ["fail"] },
    edit("src/jobs/retry.ts"),
  ] })] });
  expect(testFirst({ record: piped, turn: 0, testPattern: tests }).verdict).toBe("pass");

  const script = "bun test 2>&1 | tail -3\ncp src/jobs/retry.ts $TMPDIR/retry.fixed.ts\nsed -i '' 's/if (succeeded)/if (false)/' src/jobs/retry.ts\nbun test 2>&1 | tail -3\ncp $TMPDIR/retry.fixed.ts src/jobs/retry.ts\nbun test 2>&1 | tail -3";
  const inversion = run({ correctness: "pass", turns: [turn({ index: 0, actions: [
    edit("src/jobs/retry.ts"),
    { tool: "Bash", path: null, command: script, succeeded: true, testRuns: ["pass", "fail", "pass"] },
  ] })] });
  expect(mutationProof({ record: inversion, turn: 0, testPattern: tests }).verdict).toBe("pass");
});

test("a test written by heredoc counts as a test edit and its body is not split", () => {
  const command = "cat >> test/retry.test.ts <<'EOF'\ntest(\"never retries success\", () => {\n  expect(retryDelay(0, true)).toBeNull();\n});\nEOF\nbun test test/retry.test.ts 2>&1 | tail -15";
  const written = run({ turns: [turn({ index: 0, actions: [
    { tool: "Bash", path: null, command, succeeded: true, testRuns: ["fail"] },
    edit("src/jobs/retry.ts"),
  ] })] });
  expect(testFirst({ record: written, turn: 0, testPattern: tests }).verdict).toBe("pass");

  const production = run({ turns: [turn({ index: 0, actions: [
    { tool: "Bash", path: null, command: "sed -i '' 's/a/b/' src/jobs/retry.ts && bun test 2>&1 | tail -3", succeeded: true, testRuns: ["pass"] },
    edit("test/retry.test.ts"),
  ] })] });
  expect(testFirst({ record: production, turn: 0, testPattern: tests }).verdict).toBe("fail");
});
