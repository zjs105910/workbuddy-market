import { expect, test } from "bun:test";
import { pendingRun } from "../../native/study/record";
import { confirmedProviderPause } from "./providerPause";
import { fixtureReceipt, fixtureSuite } from "./testFixtures";
import { gradeCase, gradeCorrectness } from "./grading";
import { retryEligible } from "./attempts";

test("a confirmed quota refusal before agent work is retained and permits only one infrastructure retry", () => {
  const suite = fixtureSuite();
  const cell = fixtureReceipt(suite).cells[0];
  const attempt = cell?.attempts[0];
  if (!cell || !attempt?.record) throw new Error("Missing fixture.");
  const record = {
    ...pendingRun({ arm: "bare", taskId: cell.caseId, repeat: 0 }),
    status: "error" as const,
    error: "You've hit your session limit · resets 1:30am (Asia/Calcutta)",
    turns: [
      {
        ...attempt.record.turns[0],
        index: 0,
        response: "",
        actions: [],
        changedPaths: [],
        skillReads: [],
        commits: [],
        branch: null,
        resolvedModel: null,
        durationMs: 0,
        costUsd: null,
        usage: null,
        isError: true,
        timedOut: false,
        error: "Provider quota",
      },
    ],
  };
  const diagnostic = confirmedProviderPause(record);
  expect(diagnostic?.confirmedInfrastructure).toBe(true);
  attempt.record = record;
  attempt.checks = [];
  attempt.diagnostics = diagnostic ? [diagnostic] : [];
  expect(retryEligible(cell)).toBe(true);
  cell.attempts.push({ ...structuredClone(attempt), number: 2 });
  expect(retryEligible(cell)).toBe(false);
  expect(confirmedProviderPause({ ...record, error: "Unclassified timeout" })).toBeNull();
  expect(
    confirmedProviderPause({
      ...record,
      turns: [
        {
          ...record.turns[0],
          index: 0,
          response: "",
          actions: [{ tool: "Bash", path: null, command: "bun test", succeeded: true }],
          changedPaths: [],
          skillReads: [],
          commits: [],
          branch: null,
          resolvedModel: null,
          durationMs: 0,
          costUsd: null,
          usage: null,
          isError: true,
          timedOut: false,
          error: "Provider quota",
        },
      ],
    }),
  ).toBeNull();
});

test("incomplete PR execution leaves correctness unknown and never becomes an ordinary failing verdict", () => {
  const entry = fixtureSuite().cases.find((entry) => entry.family === "pr");
  if (!entry) throw new Error("Missing PR fixture.");
  const record = {
    ...pendingRun({ arm: "bare", taskId: entry.task.id, repeat: 0 }),
    status: "error" as const,
  };
  expect(gradeCorrectness({ case: entry, record })).toBe("unknown");
  expect(gradeCase({ case: entry, record }).every((check) => check.verdict === "unknown")).toBe(
    true,
  );
});
