import {
  pendingRun,
  type RunRecord,
  type StudyAction,
  type TurnRecord,
} from "../../native/study/record";
import type { PreferenceCase } from "./schema";

export function referenceRecord(entry: PreferenceCase): RunRecord {
  const commit = {
    hash: "fixture-commit",
    subject: "fix: correct fixture behavior",
    body: "",
    trailers: "",
  };
  const actions: StudyAction[] = entry.task.id.includes("temporary-override")
    ? []
    : [
        { tool: "Write", path: "regression.test.ts", command: null, succeeded: true },
        {
          tool: "Bash",
          path: null,
          command: "bun test regression.test.ts",
          succeeded: false,
          testRuns: ["fail"],
        },
      ];
  actions.push({ tool: "Edit", path: "src/subject.ts", command: null, succeeded: true });
  const authorized = entry.task.checks.some(
    (item) => item.kind === "commit-shape" || item.kind === "pull-request",
  );
  const turn: TurnRecord = {
    index: 0,
    response:
      entry.task.id === "length-explicit-override"
        ? `Stable comparator ${Array.from({ length: 248 }, () => "word").join(" ")}`
        : "Default sort uses string conversion. Numeric comparator: (a, b) => a - b. Proposed commit: `fix: correct fixture behavior`",
    actions,
    skillReads: [],
    changedPaths: ["src/subject.ts"],
    commits: authorized ? [commit] : [],
    branch: entry.task.git?.checkout ?? null,
    resolvedModel: "synthetic",
    durationMs: 1,
    costUsd: 0,
    usage: null,
    isError: false,
    timedOut: false,
    error: null,
  };
  const body =
    entry.task.id === "pr-current-format-override"
      ? "Correct the increment behavior and verify the change."
      : "## Changes\n- [x] Correct the fixture behavior.\n";
  return {
    ...pendingRun({ arm: "deep", taskId: entry.task.id, repeat: 0 }),
    status: "complete",
    correctness: "pass",
    safety: "pass",
    turns: [turn],
    commits: turn.commits,
    files: (entry.task.acceptance?.reference ?? []).map((file) => ({
      path: file.path,
      before:
        entry.task.git?.branches
          .flatMap((branch) => branch.commits.flatMap((item) => item.files))
          .find((item) => item.path === file.path)?.content ?? null,
      after: file.content,
    })),
    toolCalls:
      entry.family === "pr"
        ? [
            {
              tool: "gh",
              args: [
                "pr",
                "create",
                "--draft",
                "--title",
                "fix: correct fixture behavior",
                "--body",
                body,
              ],
              body,
            },
          ]
        : [],
  };
}
