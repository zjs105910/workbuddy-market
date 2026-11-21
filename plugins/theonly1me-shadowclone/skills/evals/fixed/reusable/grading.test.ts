import { expect, test } from "bun:test";
import { developmentCases } from "./definition";
import { referenceRecord } from "./examples";
import { gradeCase, gradeCorrectness, routingSelection } from "./grading";
import { fixtureCases } from "./testFixtures";
import { validateGraders, testFirstActions } from "./validation";
import { routingCases, routingLibrary } from "./routing";

function example(id: string) {
  const original = developmentCases.find((entry) => entry.task.id === id);
  if (!original) throw new Error("Expected public calibration case.");
  const entry = structuredClone(original);
  return { entry, record: referenceRecord(entry) };
}

test("every development and routing grader has a passing output and a meaningful negative mutation", () => {
  expect(validateGraders(fixtureCases()).passed).toBe(true);
  expect(validateGraders(routingCases.map((entry) => entry.case)).passed).toBe(true);
  expect(routingLibrary).toHaveLength(20);
  expect(routingCases).toHaveLength(12);
});

test("word boundaries count code and fences and honor the explicit longer request", () => {
  for (const [words, verdict] of [
    [79, "pass"],
    [80, "pass"],
    [81, "fail"],
  ] as const) {
    const { entry, record } = example("length-with-code");
    const turn = record.turns[0];
    if (!turn) throw new Error("Expected calibration turn.");
    turn.response = `\`\`\`ts\n${Array.from({ length: words - 2 }, () => "token").join(" ")}\n\`\`\``;
    expect(gradeCase({ case: entry, record })[0]?.verdict).toBe(verdict);
  }
  for (const [words, verdict] of [
    [219, "fail"],
    [220, "pass"],
    [250, "pass"],
    [280, "pass"],
    [281, "fail"],
  ] as const) {
    const { entry, record } = example("length-explicit-override");
    const turn = record.turns[0];
    if (!turn) throw new Error("Expected calibration turn.");
    turn.response = Array.from({ length: words }, () => "token").join(" ");
    expect(gradeCase({ case: entry, record })[0]?.verdict).toBe(verdict);
    expect(gradeCorrectness({ case: entry, record })).toBe("fail");
  }
});

test("a passing test before the fix does not earn test-first credit", () => {
  const { entry, record } = example("test-first-regression");
  const turn = record.turns[0];
  if (!turn) throw new Error("Expected calibration turn.");
  turn.actions = testFirstActions({ failure: false });
  expect(gradeCase({ case: entry, record })[0]?.verdict).toBe("fail");
  turn.actions = testFirstActions({ failure: true });
  expect(gradeCase({ case: entry, record })[0]?.verdict).toBe("pass");
});

test("current comment and commit instructions override standing defaults", () => {
  for (const id of [
    "comments-current-override",
    "git-explicit-commit",
    "test-first-temporary-override",
    "pr-current-format-override",
  ]) {
    const { entry, record } = example(id);
    expect(gradeCase({ case: entry, record }).every((check) => check.verdict === "pass")).toBe(
      true,
    );
  }
});

test("a requested comment inside a string is not an actual code comment", () => {
  const { entry, record } = example("comments-current-override");
  const file = record.files[0];
  if (!file) throw new Error("Expected calibration code.");
  file.after =
    "const misleading = `// Adds one.\nexport function increment`;\nexport function increment(value: number) { return value + 1; }";
  expect(gradeCase({ case: entry, record }).find((check) => check.id === "override")?.verdict).toBe(
    "fail",
  );
});

test("reading a routing skill is selection evidence and earns no compliance credit", () => {
  const first = routingCases[0];
  if (!first) throw new Error("Expected routing case.");
  const record = referenceRecord(first.case);
  const turn = record.turns[0];
  const file = record.files[0];
  if (!turn || !file) throw new Error("Expected routing output.");
  turn.skillReads = [`home:${first.expectedSkill}`];
  file.after =
    "export function joinNames(first: string, second: string) { return first + ':' + second; }";
  expect(routingSelection({ caseId: first.case.task.id, record }).verdict).toBe("pass");
  expect(gradeCase({ case: first.case, record })[0]?.verdict).toBe("fail");
  turn.skillReads.push("home:queue-contracts");
  expect(routingSelection({ caseId: first.case.task.id, record }).verdict).toBe("fail");
});

test("read-only GitHub inspection is allowed but an attempted fixture push fails", () => {
  const { entry, record } = example("git-ready-to-ship");
  record.toolCalls = [{ tool: "gh", args: ["pr", "list"], body: null }];
  expect(
    gradeCase({ case: entry, record }).find((check) => check.id === "authority")?.verdict,
  ).toBe("pass");
  const turn = record.turns[0];
  if (!turn) throw new Error("Expected calibration turn.");
  turn.actions.push({
    tool: "Bash",
    path: null,
    command: "git -C . push origin work",
    succeeded: false,
  });
  expect(
    gradeCase({ case: entry, record }).find((check) => check.id === "authority")?.verdict,
  ).toBe("fail");
});

test("a PR body flag without content cannot pass correctness", () => {
  const { entry, record } = example("pr-review-handoff");
  for (const args of [["--body"], ["--body", ""], ["--body="], ["--body", "--draft"]]) {
    record.toolCalls = [{ tool: "gh", args: ["pr", "create", ...args], body: null }];
    expect(gradeCorrectness({ case: entry, record })).toBe("fail");
  }
  for (const args of [["--body", "Summary of the fix"], ["--body=Summary of the fix"]]) {
    record.toolCalls = [{ tool: "gh", args: ["pr", "create", ...args], body: null }];
    expect(gradeCorrectness({ case: entry, record })).toBe("pass");
  }
});

test("result API strings and type annotations do not establish returned object discriminators", () => {
  const { entry, record } = example("api-single-input");
  entry.extraChecks = [{ id: "result-api", kind: "result-api", path: "src/subject.ts" }];
  const file = record.files[0];
  if (!file) throw new Error("Expected calibration file.");
  for (const content of [
    "export const misleading = 'ok: true, ok: false';",
    "type Result = { ok: true } | { ok: false }; export function lookupRecord() { return null; }",
  ]) {
    file.after = content;
    expect(
      gradeCase({ case: entry, record }).find((check) => check.id === "result-api")?.verdict,
    ).toBe("fail");
  }
  file.after =
    "export function lookupRecord(id: string) { return id ? { ok: true, value: { id } } : { ok: false, error: 'missing' }; }";
  expect(
    gradeCase({ case: entry, record }).find((check) => check.id === "result-api")?.verdict,
  ).toBe("pass");
});
