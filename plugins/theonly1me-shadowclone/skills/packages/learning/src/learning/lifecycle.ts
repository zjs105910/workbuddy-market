import path from "node:path";
import {
  readEffectiveConfig,
  type SourceId,
  fingerprint,
  readLocalText,
  acquireLocalLock,
} from "@shadowclone/core";
import type { LearningExecution } from "@shadowclone/agents";
import {
  environmentFile,
  type EnvironmentState,
  type LearningRecord,
  publishEnvironmentRevision,
  readEnvironment,
  recordFingerprint,
  renderEnvironment,
} from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import { redactSecrets } from "@shadowclone/redact";
import { isOriginBlocked, resolveRepository, type GitRemoteReader } from "@shadowclone/sessions";
import { publishReviewedLearning } from "./publication";
import { profileRulePath } from "@shadowclone/profile";
import { parseProfileRejectionText } from "@shadowclone/profile";
import { renderProfileRejections } from "@shadowclone/profile";
import { pendingLearningFile, readPendingLearning } from "./pending";

export type PreferenceEdit = {
  readonly kind: "retire" | "replace" | "narrow";
  readonly key: string;
  readonly text?: string;
};

export type PreferencePreview = {
  readonly fingerprint: string;
  readonly changes: readonly { readonly before: LearningRecord; readonly after: LearningRecord }[];
  readonly rejectedPendingKeys?: readonly string[];
};

function retiredRecord(record: LearningRecord): LearningRecord {
  return {
    ...record,
    rule: { ...record.rule, status: "stale", proposal: null },
    retirementRequested: true,
  };
}

export async function previewPreferenceEdit(options: {
  readonly paths: ProjectPaths;
  readonly edit: PreferenceEdit;
  readonly cwd?: string;
  readonly readRemote?: GitRemoteReader;
}): Promise<PreferencePreview> {
  const state = await readEnvironment(options.paths);
  const record = state?.records.find(({ rule }) => rule.key === options.edit.key);
  if (!state || !record) throw new Error("Active learned rule was not found");
  if (options.edit.kind === "retire") {
    return { fingerprint: fingerprint(renderEnvironment(state)), changes: [{ before: record, after: retiredRecord(record) }] };
  }

  const text = options.edit.kind === "replace" ? options.edit.text?.trim() : record.rule.body;
  if (!text || Buffer.byteLength(text) > 8_192) throw new Error("Replacement guidance must contain between 1 and 8192 bytes");
  const body = redactSecrets({ text });
  const confirmed: LearningRecord = {
    ...record,
    retirementRequested: undefined,
    captureSources: [],
    provenanceComplete: true,
    rule: {
      ...record.rule,
      body,
      source: "user",
      status: "active",
      proposal: null,
      evidence: { for: [], against: [] },
      observations: 0,
      sessions: 0,
    },
  };

  if (options.edit.kind === "replace") {
    return { fingerprint: fingerprint(renderEnvironment(state)), changes: [{ before: record, after: confirmed }] };
  }

  const { config, policy } = await readEffectiveConfig({
    configPath: options.paths.configFile, managedConfigPath: options.paths.managedConfigFile,
  });
  if (!config.sources["git-metadata"]) throw new Error("Enable repository metadata consent before narrowing guidance");
  const repository = await resolveRepository({
    cwd: options.cwd ?? process.cwd(), enabled: true, readRemote: options.readRemote,
  });
  if (!repository.profileFileName || !repository.origin.promotable ||
    isOriginBlocked({ repository, patterns: policy.blockedOrigins })) {
    throw new Error("Narrowing needs a verified, permitted repository");
  }
  if (record.rule.scope === "project" ||
    (record.rule.scope === "org" && record.rule.originDirectory !== repository.origin.directoryName)) {
    throw new Error("This change would move the rule across repository boundaries");
  }
  const narrowed: LearningRecord = {
    ...confirmed,
    rule: {
      ...confirmed.rule,
      key: `narrowed-${fingerprint(JSON.stringify([record.rule.key, repository.id])).slice(0, 24)}`,
      scope: "project",
      originDirectory: repository.origin.directoryName,
      repositoryName: repository.profileFileName,
    },
  };
  return {
    fingerprint: fingerprint(renderEnvironment(state)),
    changes: [
      { before: record, after: retiredRecord(record) },
      { before: record, after: narrowed },
    ],
  };
}

function applyDecision(options: {
  readonly state: EnvironmentState;
  readonly preview: PreferencePreview;
}): EnvironmentState {
  const records = new Map(options.state.records.map((record) => [record.rule.key, record]));
  const dispositions = [...options.state.dispositions];
  const rejected = new Set(options.state.rejected);
  const rejections = new Map(parseProfileRejectionText(options.state.rejectionText).map((entry) => [entry.key, entry]));
  for (const { after } of options.preview.changes) {
    records.set(after.rule.key, after);
    if (after.retirementRequested) {
      rejected.add(after.rule.key);
      rejections.set(after.rule.key, {
        key: after.rule.key,
        relativePath: profileRulePath(after.rule),
        title: after.rule.title,
        body: after.rule.body,
        source: after.rule.source,
        importReference: after.rule.importReference,
        reason: "user-rejected",
      });
    } else {
      rejected.delete(after.rule.key);
      rejections.delete(after.rule.key);
    }
    const published = options.state.dispositions.some((entry) =>
      entry.key === after.rule.key && entry.status === "published",
    );
    if (after.retirementRequested && !published) {
      const previous = dispositions.filter((entry) => entry.key === after.rule.key);
      for (const entry of previous) {
        dispositions.push({
          ...entry,
          inputFingerprint: recordFingerprint(after),
          status: "excluded",
          reason: "Explicitly retired; independently existing guidance was preserved.",
        });
      }
    }
  }
  return {
    ...options.state, records: [...records.values()], dispositions,
    rejected: [...rejected], rejectionText: renderProfileRejections([...rejections.values()]),
  };
}

export async function applyPreferencePreview(options: {
  readonly paths: ProjectPaths;
  readonly preview: PreferencePreview;
  readonly execution?: LearningExecution;
  readonly readRemote?: GitRemoteReader;
}): Promise<{ readonly revision: string | null; readonly applied: number; readonly pending: number }> {
  const { policy } = await readEffectiveConfig({
    configPath: options.paths.configFile, managedConfigPath: options.paths.managedConfigFile,
  });
  if (!policy.enabled) throw new Error("Managed policy blocks preference changes");
  const pendingLock = await acquireLocalLock(path.join(options.paths.shadowcloneDirectory, "learning-pending.db"));
  if (!pendingLock) throw new Error("Another learning review is running");
  const lock = await acquireLocalLock(path.join(options.paths.shadowcloneDirectory, "environment-write.db"));
  if (!lock) {
    pendingLock.release();
    throw new Error("Another learning update is running");
  }
  let revision: string | null;
  try {
    const state = await readEnvironment(options.paths);
    const pending = options.preview.rejectedPendingKeys === undefined
      ? null : await readPendingLearning(options.paths);
    const currentFingerprint = state === null ? null : fingerprint(
      renderEnvironment(state) + (pending === null ? "" : JSON.stringify(pending)),
    );
    if (!state || currentFingerprint !== options.preview.fingerprint) {
      throw new Error("Learning changed since preview. Review the new change before applying it.");
    }
    const filePath = environmentFile(options.paths);
    const rejectedKeys = new Set(options.preview.rejectedPendingKeys ?? []);
    const pendingPath = pendingLearningFile(options.paths);
    revision = await publishEnvironmentRevision({
      paths: options.paths,
      updates: [{
        filePath,
        previous: await readLocalText(filePath),
        next: renderEnvironment(applyDecision({ state, preview: options.preview })),
      }, ...(pending === null ? [] : [{
        filePath: pendingPath,
        previous: await readLocalText(pendingPath),
        next: `${JSON.stringify({
          ...pending,
          rules: pending.rules.filter((rule) => !rejectedKeys.has(rule.key)),
          rejectedKeys: [...new Set([...pending.rejectedKeys, ...rejectedKeys])],
        }, null, 2)}\n`,
      }])],
    });
  } finally {
    lock.release();
    pendingLock.release();
  }
  const publication = await publishReviewedLearning({
    ...options, keys: options.preview.changes.map(({ after }) => after.rule.key),
  });
  return { revision, ...publication };
}

export async function previewSourceRemoval(options: {
  readonly paths: ProjectPaths;
  readonly source: SourceId;
}) {
  const state = await readEnvironment(options.paths);
  if (!state) throw new Error("Run migrate skills before reviewing learned-source removal");
  const affected = state.records.filter((record) =>
    !record.retirementRequested && record.captureSources?.includes(options.source),
  );
  const pending = await readPendingLearning(options.paths);
  return {
    source: options.source,
    mixed: [
      ...affected.filter((record) => record.captureSources?.length !== 1).map(({ rule }) => rule.key),
      ...pending.rules.filter((rule) => {
        const provenance = pending.provenance[rule.key];
        return provenance?.sources.includes(options.source) && provenance.sources.length > 1;
      }).map((rule) => rule.key),
    ],
    unresolved: state.records.filter((record) => record.rule.source === "mined" &&
      record.provenanceComplete !== true).map(({ rule }) => rule.key),
    preview: {
      fingerprint: fingerprint(renderEnvironment(state) + JSON.stringify(pending)),
      rejectedPendingKeys: pending.rules.filter((rule) => {
        const provenance = pending.provenance[rule.key];
        return provenance?.complete && provenance.sources.length === 1 && provenance.sources[0] === options.source;
      }).map((rule) => rule.key),
      changes: affected.filter((record) => record.provenanceComplete === true &&
        record.captureSources?.length === 1).map((record) => ({ before: record, after: retiredRecord(record) })),
    },
  };
}
