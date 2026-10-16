import { expect, test } from "bun:test";
import { studyTask } from "../fixtures";
import { run, turn } from "./fixtures";
import { deterministicChecks } from "./index";

test("an errored later turn retains checks observed in an earlier turn", () => {
  const task = studyTask({
    checks: [
      { id: "short-answer", keyItem: "concise-answers", kind: "max-words", turn: 0, maximum: 5 },
      { id: "commit-shape", keyItem: "commit-subject-shape", kind: "commit-shape", afterTurn: 1, subjectOnly: true, subject: "^[a-z]+: [a-z]", forbidden: [] },
    ],
  });
  const record = run({
    status: "error",
    turns: [turn({ index: 0, response: "The change is small." })],
  });

  expect(deterministicChecks({ record, task }).map((check) => check.verdict))
    .toEqual(["pass", "unknown"]);
});
