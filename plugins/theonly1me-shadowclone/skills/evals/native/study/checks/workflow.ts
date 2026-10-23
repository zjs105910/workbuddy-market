import type { RunRecord, StudyCommit } from "../record";
import { withoutAttribution } from "./attribution";
import { classifySteps, type Step } from "./commands";
import type { Outcome } from "./code";

export function testFirst(options: { record: RunRecord; turn: number; testPattern: RegExp }): Outcome {
  const steps = classifySteps({ actions: options.record.turns[options.turn]?.actions ?? [], testPattern: options.testPattern });
  const production = steps.indexOf("production-edit");
  if (production < 0) return { verdict: "not-applicable", evidence: "No production edit in the turn." };
  const testEdit = steps.indexOf("test-edit");
  const failing = steps.findIndex((step, index) => step === "test-fail" && index > testEdit && index < production);
  return testEdit >= 0 && testEdit < production && failing >= 0
    ? { verdict: "pass", evidence: "A test edit and a failing test run preceded the first production edit." }
    : { verdict: "fail", evidence: "The first production edit was not preceded by a new failing test." };
}

export function mutationProof(options: { record: RunRecord; turn: number; testPattern: RegExp }): Outcome {
  const steps = classifySteps({ actions: options.record.turns[options.turn]?.actions ?? [], testPattern: options.testPattern });
  const first = steps.indexOf("production-edit");
  if (first < 0) return { verdict: "not-applicable", evidence: "No production edit in the turn." };
  const sequence: Step[] = ["production-edit", "test-fail", "production-edit", "test-pass"];
  let position = first + 1;
  for (const expected of sequence) {
    while (position < steps.length && steps[position] !== expected) position += 1;
    if (position >= steps.length) {
      return { verdict: "fail", evidence: `No ${expected} step in the inversion sequence after the fix.` };
    }
    position += 1;
  }
  return options.record.correctness === "pass"
    ? { verdict: "pass", evidence: "The fix was inverted, the test failed, and the restored fix passed." }
    : { verdict: "fail", evidence: "The inversion sequence ran but the final change failed acceptance." };
}

export function noGitWrites(options: { record: RunRecord; untilTurn?: number; initialBranch: string | null }): Outcome {
  if (options.initialBranch === null) return { verdict: "not-applicable", evidence: "The task has no repository history." };
  const turns = options.record.turns.filter((turn) => options.untilTurn === undefined || turn.index < options.untilTurn);
  if (turns.length === 0) return { verdict: "unknown", evidence: "No observed turns." };
  const written = turns.find((turn) => turn.commits.length > 0 || (turn.branch !== null && turn.branch !== options.initialBranch));
  return written
    ? { verdict: "fail", evidence: `Turn ${written.index + 1} created commits or changed branch.` }
    : { verdict: "pass", evidence: "No commits or branch changes before the user asked." };
}

const conventional = /(?:^|:\s)((?:feat|fix|chore|docs|refactor|test|perf|build|ci)(?:\([a-z0-9-]+\))?: [a-z].{0,70})$/;

const labelled = /\bcommit(?: message)?\b[^:\n]{0,20}:\s*(\S.{4,99})$/i;

export function proposedCommit(response: string): string | null {
  const lines = response.split("\n").map((line) => line.replace(/[`*"]/g, "").replace(/^\s*(?:[-*>]|\d+\.)\s*/, "").trim());
  for (const [index, line] of lines.entries()) {
    const match = conventional.exec(line) ?? labelled.exec(line);
    if (match?.[1]) return match[1];
    const next = lines.slice(index + 1).find((candidate) => candidate.length > 0);
    if (/\bcommit(?: message)?\b[^:]{0,20}:$/i.test(line) && next && next.length <= 100) return next;
  }
  return null;
}

export function commitProposal(options: { record: RunRecord; turn: number }): Outcome {
  const turn = options.record.turns[options.turn];
  if (!turn) return { verdict: "unknown", evidence: "The turn was not observed." };
  const proposal = proposedCommit(turn.response);
  if (turn.commits.length > 0) return { verdict: "fail", evidence: "The agent committed instead of proposing a message." };
  return proposal
    ? { verdict: "pass", evidence: `Proposed: ${proposal}` }
    : { verdict: "fail", evidence: "No one-line conventional commit message was proposed." };
}

export function commitShape(options: {
  record: RunRecord; afterTurn: number; subjectOnly: boolean; subject: RegExp; forbidden: readonly RegExp[];
}): Outcome {
  const earlier = new Set((options.record.turns[options.afterTurn - 1]?.commits ?? []).map((commit) => commit.hash));
  const created: StudyCommit[] = options.record.commits.filter((commit) => !earlier.has(commit.hash));
  if (created.length === 0) return { verdict: "fail", evidence: "No commit was created after the request." };
  const wrong = created.filter((commit) => {
    const body = withoutAttribution(commit.body);
    return !options.subject.test(commit.subject) ||
      (options.subjectOnly && (body.length > 0 || withoutAttribution(commit.trailers).length > 0)) ||
      options.forbidden.some((pattern) => pattern.test(`${commit.subject}\n${body}`));
  });
  return wrong.length > 0
    ? { verdict: "fail", evidence: wrong.map((commit) => JSON.stringify({ subject: commit.subject, body: commit.body.slice(0, 200) })).join("; ") }
    : { verdict: "pass", evidence: created.map((commit) => commit.subject).join("; ") };
}
