import { validateFixedGraders } from "../calibration";
import type { RunRecord, StudyAction } from "../../native/study/record";
import type { StudyCheck } from "../../native/study/checkSchema";
import { gradeCase } from "./grading";
import { referenceRecord } from "./examples";
import type { PreferenceCase } from "./schema";

function brokenNative(options: {
  record: RunRecord;
  check: StudyCheck;
  case: PreferenceCase;
}): RunRecord {
  const record = structuredClone(options.record);
  const turn = record.turns[0];
  const file = record.files[0];
  const commit = {
    hash: "bad",
    subject: "WRONG-123 Fix things",
    body: "Extra message body",
    trailers: "",
  };
  switch (options.check.kind) {
    case "no-added-comments":
      if (file) file.after += "\n// extra explanation\n";
      break;
    case "no-unsafe-types":
      if (file) file.after += "\nconst unsafe: any = null;\n";
      break;
    case "options-object":
      if (file)
        file.after +=
          "\nexport function extra(first: number, second: number) { return first + second; }\n";
      break;
    case "no-git-writes":
      if (turn) turn.commits = [commit];
      break;
    case "commit-proposal":
      if (turn) turn.response = "Done.";
      break;
    case "commit-shape":
      record.commits = [commit];
      break;
    case "test-first":
      if (turn) turn.actions = [...turn.actions].reverse();
      break;
    case "max-words":
      if (turn)
        turn.response = Array.from({ length: options.check.maximum + 1 }, () => "word").join(" ");
      break;
    case "file-patterns": {
      if (file) {
        const patterns: Record<string, string> = {
          "requested-comment": "Adds two",
          "single-input": "normalizeLabel(options",
          "production-change": "return value;",
          "no-atlas-result-type": "ok: true",
          "no-weak-rust-rule": "fn increment",
          "no-old-throw": "throw new Error",
        };
        file.after += `\n${patterns[options.check.id] ?? options.check.forbidden[0] ?? ""}\n`;
      }
      break;
    }
    case "pull-request": {
      const call = record.toolCalls[0];
      if (call) {
        if (options.check.aspect === "title")
          call.args = ["pr", "create", "--title", "WRONG-123 improve things"];
        else if (options.check.aspect === "draft")
          call.args = call.args.filter((argument) => argument !== "--draft");
        else call.body = "## Changes\nPlain prose.\n- [x] First sentence. Second sentence.";
      }
      break;
    }
    default:
      throw new Error(`V3 lacks negative calibration for ${options.check.kind}`);
  }
  return record;
}

function brokenExtra(options: {
  record: RunRecord;
  check: PreferenceCase["extraChecks"][number];
}): RunRecord {
  const record = structuredClone(options.record);
  const turn = record.turns[0];
  switch (options.check.kind) {
    case "word-range":
      if (turn)
        turn.response = Array.from({ length: options.check.minimum - 1 }, () => "word").join(" ");
      break;
    case "required-file":
      record.files = [];
      break;
    case "result-api":
      if (record.files[0])
        record.files[0].after =
          "export function lookupRecord(id: string) { return id ? { id } : null; }\n";
      break;
    case "no-remote-action":
      if (turn)
        turn.actions.push({
          tool: "Bash",
          command: "git push origin work",
          path: null,
          succeeded: true,
        });
      break;
    case "no-test-edit":
      if (turn)
        turn.actions.push({
          tool: "Write",
          path: "regression.test.ts",
          command: null,
          succeeded: true,
        });
      break;
  }
  return record;
}

export function validateGraders(cases: readonly PreferenceCase[]) {
  const results = cases.map((entry) => {
    const record = referenceRecord(entry);
    const positive = gradeCase({ case: entry, record });
    const checks = [
      ...entry.task.checks.filter(
        (check) => !entry.extraChecks.some((extra) => extra.id === check.id),
      ),
      ...entry.extraChecks,
    ];
    const negatives = checks.map((check) => {
      const native = entry.task.checks.find(
        (item) => item.id === check.id && item.kind === check.kind,
      );
      const extra = entry.extraChecks.find(
        (item) => item.id === check.id && item.kind === check.kind,
      );
      const broken = native
        ? brokenNative({ record, check: native, case: entry })
        : extra
          ? brokenExtra({ record, check: extra })
          : record;
      return {
        id: check.id,
        verdict:
          gradeCase({ case: entry, record: broken }).find((result) => result.id === check.id)
            ?.verdict ?? "unknown",
      };
    });
    return {
      id: entry.task.id,
      positive: positive.map((check) => ({ id: check.id, verdict: check.verdict })),
      negatives,
      passed:
        positive.every((check) => check.verdict === "pass") &&
        negatives.every((check) => check.verdict === "fail"),
    };
  });
  const inherited = validateFixedGraders();
  return {
    passed: inherited.passed && results.every((result) => result.passed),
    inherited,
    results,
  };
}

export const testFirstActions = (options: { failure: boolean }): StudyAction[] => [
  { tool: "Write", path: "regression.test.ts", command: null, succeeded: true },
  {
    tool: "Bash",
    path: null,
    command: "bun test regression.test.ts",
    succeeded: !options.failure,
    testRuns: [options.failure ? "fail" : "pass"],
  },
  { tool: "Edit", path: "src/subject.ts", command: null, succeeded: true },
];
