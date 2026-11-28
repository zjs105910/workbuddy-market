import { profileEvidenceId, type ProfileSnapshot } from "@shadowclone/profile";
import type { SeedGuidance, SeedLibrary } from "@shadowclone/skills";
import { seedGuidanceProfileKey } from "@shadowclone/skills";
import type { DistillBatch } from "../batch";
import type {
  PromptAxisOption,
  PromptEvidence,
  PromptRejection,
  PromptRule,
  ReconciliationContext,
} from "./types";

const sectionFiles = new Set([
  "engineering.md",
  "workflow.md",
  "boundaries.md",
]);

function inBatchScope(options: {
  readonly relativePath: string;
  readonly batch: DistillBatch;
}): boolean {
  const segments = options.relativePath.split("/");

  if (segments[0] === "global") {
    return segments.length === 2 && sectionFiles.has(segments[1] ?? "");
  }

  if (
    segments[0] !== "org" ||
    segments[1] !== options.batch.origin.directoryName
  ) {
    return false;
  }

  if (segments.length === 3) {
    return sectionFiles.has(segments[2] ?? "");
  }

  return (
    options.batch.repositoryName !== null &&
    segments.length === 4 &&
    segments[2] === "projects" &&
    segments[3] === `${options.batch.repositoryName}.md`
  );
}

function ruleInBatch(options: {
  readonly rule: ProfileSnapshot["rules"][number]["rule"];
  readonly batch: DistillBatch;
}): boolean {
  if (options.rule.scope === "global") {
    return true;
  }

  if (options.rule.originDirectory !== options.batch.origin.directoryName) {
    return false;
  }

  return (
    options.rule.scope === "org" ||
    options.rule.repositoryName === options.batch.repositoryName
  );
}

function guidanceBody(guidance: SeedGuidance): string {
  return guidance.kind === "skill"
    ? guidance.body.replace(/^## /gm, "### ")
    : guidance.body;
}

function axisOptions(options: {
  readonly key: string;
  readonly library: SeedLibrary;
}): readonly PromptAxisOption[] {
  const current = options.library.guidance.find(
    (guidance) => seedGuidanceProfileKey(guidance.id) === options.key,
  );

  if (!current?.axis) {
    return [];
  }

  const axis = options.library.axes.find((entry) => entry.id === current.axis);

  return (axis?.guidance ?? [])
    .filter((guidance) => guidance.id !== current.id)
    .map((guidance, index) => ({
      token: `option-${index + 1}`,
      title: guidance.title,
      body: guidanceBody(guidance),
      appliesWhen: guidance.appliesWhen,
    }));
}

export function createReconciliationContext(options: {
  readonly batch: DistillBatch;
  readonly profile: ProfileSnapshot;
  readonly library: SeedLibrary;
}): ReconciliationContext {
  const rules: PromptRule[] = options.profile.rules
    .filter((entry) => ruleInBatch({ rule: entry.rule, batch: options.batch }))
    .map((snapshot, index) => ({
      token: `rule-${index + 1}`,
      snapshot,
      axisOptions: axisOptions({
        key: snapshot.rule.key,
        library: options.library,
      }),
    }));

  const rejections: PromptRejection[] = options.profile.rejections
    .filter((entry) =>
      inBatchScope({
        relativePath: entry.rejection.relativePath,
        batch: options.batch,
      }),
    )
    .map((snapshot, index) => ({ token: `rejection-${index + 1}`, snapshot }));

  const evidence: PromptEvidence[] = options.batch.signals.map(
    (signal, index) => ({
      token: `evidence-${index + 1}`,
      signal,
      evidenceId: profileEvidenceId({
        originId: signal.origin.id,
        sessionId: signal.sessionId,
        timestamp: signal.timestamp,
        kind: signal.kind,
        category: signal.category,
      }),
    }),
  );

  return { batch: options.batch, rules, rejections, evidence };
}
