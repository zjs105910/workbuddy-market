import { deterministicChecks } from "../native/study/checks";
import { pendingRun, type RunRecord, type TurnRecord } from "../native/study/record";
import type { StudyTask } from "../native/study/schema";
import { fingerprint } from "../shared/structured";
import { fixedDefinition } from "./definition";

export function referenceRecord(task: StudyTask): RunRecord {
  const turns: TurnRecord[] = task.turns.map((_, index) => ({
    index, response: "Default sort converts values to strings. Use (left, right) => left - right for ascending numeric order.",
    actions: [], skillReads: [], changedPaths: [], commits: [], branch: task.git?.checkout ?? null, resolvedModel: null,
    durationMs: 1, costUsd: null, usage: null, isError: false, timedOut: false, error: null,
  }));
  return {
    ...pendingRun({ arm: "bare", taskId: task.id, repeat: 0 }), status: "complete", turns,
    correctness: "pass", safety: "pass",
    files: task.acceptance?.reference.map((file) => ({ path: file.path,
      before: task.git?.branches[0]?.commits[0]?.files.find((entry) => entry.path === file.path)?.content ?? null, after: file.content })) ?? [],
  };
}

function failingRecord(options: { record: RunRecord; kind: string }): RunRecord {
  const change = (text: string) => ({ ...options.record, files: options.record.files.map((file) => ({ ...file, after: `${file.after ?? ""}\n${text}\n` })) });
  switch (options.kind) {
    case "no-added-comments": return change("// Added explanation.");
    case "no-unsafe-types": return change("export const unchecked: any = 1;");
    case "options-object": return change("export function positional(left: number, right: number) { return left + right; }");
    case "no-git-writes": return { ...options.record, turns: options.record.turns.map((turn) => ({ ...turn, branch: "unexpected" })) };
    case "max-words": return { ...options.record, turns: options.record.turns.map((turn) => ({ ...turn, response: "word ".repeat(81) })) };
    case "patterns": return { ...options.record, turns: options.record.turns.map((turn) => ({ ...turn, response: "An unrelated answer." })) };
    default: throw new Error("Fixed grader has no negative example");
  }
}

export function validateFixedGraders() {
  const results = fixedDefinition.tasks.flatMap((task) => {
    const record = referenceRecord(task);
    const first = deterministicChecks({ record, task });
    const stable = fingerprint(first) === fingerprint(deterministicChecks({ record, task }));
    return task.checks.map((check) => ({ taskId: task.id, checkId: check.id, stable,
      reference: first.find((result) => result.id === check.id)?.verdict ?? "unknown",
      negative: deterministicChecks({ task, record: failingRecord({ record, kind: check.kind }) }).find((result) => result.id === check.id)?.verdict ?? "unknown" }));
  });
  return { passed: results.every((result) => result.stable && result.reference === "pass" && result.negative === "fail"), results };
}
