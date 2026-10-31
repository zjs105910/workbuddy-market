import type { CoverageEntry } from "./coverage";
import { deterministicChecks } from "./checks";
import type { MatrixReceipt } from "./matrix";
import { studyReport } from "./report";
import type { PersonalArm, StudySuite } from "./schema";
import { achievableSuite } from "./validate";

export function rescoreStudyReceipt(options: { readonly suite: StudySuite; readonly receipt: MatrixReceipt }): MatrixReceipt {
  const runs = options.receipt.runs.flatMap((run) => {
    const task = options.suite.tasks.find((entry) => entry.id === run.taskId);
    if (!task) return [];
    const checks = deterministicChecks({ record: run, task }).map((check) => {
      const definition = task.checks.find((entry) => entry.id === check.id);
      return definition?.kind === "judged" ? run.checks.find((entry) => entry.id === check.id) ?? check : check;
    });
    return [{ ...run, checks }];
  });
  return { ...options.receipt, runs };
}

export function achievableReport(options: {
  candidates: StudySuite;
  frozen: StudySuite;
  receipt: MatrixReceipt;
  coverage: Partial<Record<PersonalArm, readonly CoverageEntry[]>>;
}) {
  const suite = achievableSuite({ candidates: options.candidates, dropped: options.frozen.droppedChecks });
  return studyReport({ suite, receipt: rescoreStudyReceipt({ suite, receipt: options.receipt }), coverage: options.coverage });
}
