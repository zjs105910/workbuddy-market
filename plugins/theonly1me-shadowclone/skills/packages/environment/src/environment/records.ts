import { parseProfileRejectionText, profileRulePath } from "@shadowclone/profile";
import { commitLocalChanges } from "@shadowclone/changes";
import { fingerprint, readLocalText, acquireLocalLock } from "@shadowclone/core";
import path from "node:path";
import type { ProjectPaths, SourceId } from "@shadowclone/core";
import type {
  ProfileRule,
  ProfileRuleReference,
  ProfileWriteResult,
  ProfileSnapshot,
} from "@shadowclone/profile";
import {
  environmentFile,
  readEnvironment,
  readRedactedEnvironment,
  renderEnvironment,
} from "./store";
import { redactSecrets } from "@shadowclone/redact";
import { learningRuleSchema, type LearningRecord } from "./types";

export function recordFingerprint(record: LearningRecord): string {
  return fingerprint(JSON.stringify({
    kind: record.kind,
    rule: record.rule,
    ...(record.retirementRequested ? { retirementRequested: true } : {}),
  }));
}

export async function learningSnapshot(
  paths: ProjectPaths,
): Promise<ProfileSnapshot | null> {
  const state = await readRedactedEnvironment(paths);
  const original = await readEnvironment(paths);

  if (state === null || original === null) {
    return null;
  }

  return {
    rules: state.records.map(({ rule }) => ({
      rule,
      promptTitle: rule.title,
      promptBody: rule.body,
      promptAppliesWhen: rule.appliesWhen,
      promptProposal: rule.proposal,
    })),
    rejections: parseProfileRejectionText(original.rejectionText).map(
      (rejection) => ({
        rejection,
        promptTitle: rejection.title === null ? null : redactSecrets({ text: rejection.title }),
        promptBody: rejection.body === null ? null : redactSecrets({ text: rejection.body }),
      }),
    ),
  };
}

export async function storeLearningRules(options: {
  readonly paths: ProjectPaths;
  readonly rules: readonly ProfileRule[];
  readonly retired?: readonly ProfileRuleReference[];
  readonly provenance?: Readonly<Record<string, {
    readonly sources: readonly SourceId[];
    readonly complete: boolean;
  }>>;
}): Promise<ProfileWriteResult | null> {
  if ((await readEnvironment(options.paths)) === null) {
    return null;
  }

  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "environment-write.db"),
  );

  if (!lock) {
    throw new Error("Another learning update is running");
  }

  try {
    const state = await readEnvironment(options.paths);

    if (state === null) {
      throw new Error("Learning environment disappeared");
    }

    const records = new Map(
      state.records.map((record) => [record.rule.key, record]),
    );

    for (const retired of options.retired ?? []) {
      const record = records.get(retired.key);

      if (record && profileRulePath(record.rule) === retired.relativePath) {
        records.set(retired.key, {
          ...record,
          rule: { ...record.rule, status: "stale", proposal: null },
          retirementRequested: true,
        });
      }
    }

    for (const rule of options.rules) {
      if (state.rejected.includes(rule.key)) {
        continue;
      }

      const previous = records.get(rule.key);
      const provenance = options.provenance?.[rule.key];

      records.set(rule.key, {
        kind: previous?.kind ?? "guidance",
        sourceHash: previous?.sourceHash ?? null,
        sourceLocator: previous?.sourceLocator ?? null,
        rule: learningRuleSchema.parse(rule),
        ...(provenance ? {
          captureSources: [...provenance.sources],
          provenanceComplete: provenance.complete,
        } : {
          captureSources: previous?.captureSources,
          provenanceComplete: previous?.provenanceComplete,
        }),
      });
    }

    const filePath = environmentFile(options.paths);

    await commitLocalChanges({
      paths: options.paths,
      root: options.paths.shadowcloneDirectory,
      kind: "environment",
      updates: [
        {
          filePath,
          previous: await readLocalText(filePath),
          next: renderEnvironment({ ...state, records: [...records.values()] }),
        },
      ],
    });

    return {
      files: 1,
      rules: options.rules.length,
      rejected: state.rejected.length,
      preserved: 0,
    };
  } finally {
    lock.release();
  }
}
