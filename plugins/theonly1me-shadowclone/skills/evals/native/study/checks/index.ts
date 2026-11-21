import type { StudyCheck, StudyCheckResult } from "../checkSchema";
import type { RunRecord } from "../record";
import type { StudyTask } from "../schema";
import { fileLength, filePatterns, identifiers, introducedSyntax, optionsObject, type Outcome } from "./code";
import { maximumWords, pullRequest, responsePatterns, sentenceCount } from "./response";
import { commitProposal, commitShape, mutationProof, noGitWrites, testFirst } from "./workflow";

const pattern = (source: string) => new RegExp(source, "iu");

function outcome(options: { check: StudyCheck; record: RunRecord; task: StudyTask }): Outcome {
  const { check, record } = options;
  switch (check.kind) {
    case "no-added-comments": return introducedSyntax({ files: record.files, check: "zero-comments" });
    case "no-unsafe-types": return introducedSyntax({ files: record.files, check: "type-safety" });
    case "max-file-lines": return fileLength({ files: record.files, limit: check.limit });
    case "options-object": return optionsObject({ files: record.files });
    case "identifiers": return identifiers({ files: record.files, denylist: check.denylist });
    case "test-first": return testFirst({ record, turn: check.turn, testPattern: pattern(check.testPattern) });
    case "mutation-proof": return mutationProof({ record, turn: check.turn, testPattern: pattern(check.testPattern) });
    case "no-git-writes": return noGitWrites({
      record, initialBranch: options.task.git?.checkout ?? null, ...(check.untilTurn === undefined ? {} : { untilTurn: check.untilTurn }),
    });
    case "commit-proposal": return commitProposal({ record, turn: check.turn });
    case "commit-shape": return commitShape({
      record, afterTurn: check.afterTurn, subjectOnly: check.subjectOnly, subject: new RegExp(check.subject, "u"), forbidden: check.forbidden.map(pattern),
    });
    case "file-patterns": return filePatterns({ files: record.files, filePattern: pattern(check.files), forbidden: check.forbidden.map(pattern) });
    case "pull-request": return pullRequest({
      toolCalls: record.toolCalls, aspect: check.aspect, forbidden: check.forbidden.map(pattern),
      ...(check.checklistHeading ? { checklistHeading: check.checklistHeading } : {}),
    });
    case "max-words": return maximumWords({ record, turn: check.turn, maximum: check.maximum });
    case "patterns": return responsePatterns({
      record, turn: check.turn, extract: check.extract, required: check.required.map(pattern), forbidden: check.forbidden.map(pattern),
    });
    case "sentence-count": return sentenceCount({ record, turn: check.turn, extract: check.extract, maximum: check.maximum });
    case "judged": return { verdict: "unknown", evidence: "Awaiting blinded judgments." };
  }
}

export function deterministicChecks(options: { record: RunRecord; task: StudyTask }): StudyCheckResult[] {
  return options.task.checks.map((check) => {
    if (options.record.status !== "complete") {
      const turn = "turn" in check ? options.record.turns[check.turn] :
        "afterTurn" in check ? options.record.turns[check.afterTurn] : null;
      const observed = check.kind === "judged" ? false :
        turn !== null ? turn !== undefined && !turn.timedOut :
          check.kind === "no-git-writes" ? check.untilTurn !== undefined &&
            options.record.turns.length > check.untilTurn :
            check.kind === "pull-request" ? options.record.toolCalls.length > 0 :
              options.record.turns.length > 0 && options.record.files.length > 0;

      if (!observed) {
        return { id: check.id, keyItem: check.keyItem, verdict: "unknown", evidence: "The required agent action was not observed." };
      }
    }
    const result = outcome({ check, record: options.record, task: options.task });
    return { id: check.id, keyItem: check.keyItem, verdict: result.verdict, evidence: result.evidence.slice(0, 2000) };
  });
}
