import path from "node:path";
import { readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import type { ReferenceRecord } from "../../references";
import { parseProfileBlocks } from "../parse";
import type { ProfileRejection } from "../state";
import type { ExistingProfileRule, ProfileRule } from "../types";
import type { ProfileCurationDecision } from "./decisions";

export type ProfileCurationFile = {
  readonly previous: string | null;
  readonly blocks: readonly ReturnType<typeof parseProfileBlocks>[number][];
};

export async function readProfileCurationFiles(
  paths: ProjectPaths,
): Promise<Map<string, ProfileCurationFile>> {
  const relativePaths = await Array.fromAsync(
    new Bun.Glob("{global,org}/**/*.md").scan({
      cwd: paths.profileDirectory,
      onlyFiles: true,
      throwErrorOnBrokenSymlink: true,
    }),
  );

  const files = new Map<string, ProfileCurationFile>();

  for (const relativePath of relativePaths.sort()) {
    const previous = await readLocalText(
      path.join(paths.profileDirectory, relativePath),
    );

    files.set(relativePath, {
      previous,
      blocks: previous === null ? [] : parseProfileBlocks(previous),
    });
  }

  return files;
}

export function indexProfileCurationRules(
  files: ReadonlyMap<string, ProfileCurationFile>,
): Map<
  string,
  { readonly relativePath: string; readonly rule: ExistingProfileRule }
> {
  const rules = new Map<
    string,
    { readonly relativePath: string; readonly rule: ExistingProfileRule }
  >();

  for (const [relativePath, file] of files) {
    for (const block of file.blocks) {
      if (block.key === null) {
        continue;
      }

      if (rules.has(block.key)) {
        throw new Error("Profile contains duplicate rule keys");
      }

      rules.set(block.key, { relativePath, rule: block });
    }
  }

  return rules;
}

export function profileRuleFromDecision(
  existing: ExistingProfileRule,
  decision: Extract<ProfileCurationDecision, { readonly action: "move" }>,
): ProfileRule {
  const fields = {
    key: existing.key,
    title: existing.title,
    body: existing.body,
    section: decision.section,
    source: existing.source,
    status: existing.status,
    proposal: existing.proposal,
    appliesWhen: existing.appliesWhen,
    evidence: existing.evidence,
    observations: existing.observations,
    lastSeen: existing.lastSeen,
    sessions: existing.sessions,
    origins: existing.origins,
    importReference: existing.importReference,
  };

  const location = decision.location;

  if (location.scope === "global") {
    return {
      ...fields,
      scope: "global",
      originDirectory: null,
      repositoryName: null,
    };
  }

  if (location.scope === "org") {
    return { ...fields, ...location, repositoryName: null };
  }

  return { ...fields, ...location };
}

export function referenceFromDecision(options: {
  readonly decision: Extract<
    ProfileCurationDecision,
    { readonly action: "reference" }
  >;
  readonly body: string;
}): ReferenceRecord {
  const value = options.decision.reference;

  const fields = {
    schema: 1 as const,
    key: value.key,
    title: value.title,
    summary: value.summary,
    tags: value.tags,
    source: "user" as const,
    sourceLocator: `profile-repair/${options.decision.key}`,
    updatedAt: value.updatedAt,
    body: options.body,
  };

  if (value.location.scope === "global") {
    return {
      ...fields,
      scope: "global",
      originDirectory: null,
      repositoryName: null,
    };
  }

  if (value.location.scope === "org") {
    return { ...fields, ...value.location, repositoryName: null };
  }

  return { ...fields, ...value.location };
}

export function rejectionFromDecision(options: {
  readonly decision: Exclude<
    ProfileCurationDecision,
    { readonly action: "move" }
  >;
  readonly relativePath: string;
  readonly rule: ExistingProfileRule;
}): ProfileRejection {
  return {
    relativePath: options.relativePath,
    key: options.rule.key,
    title: options.rule.title,
    body: options.rule.body,
    source: options.rule.source,
    importReference: options.rule.importReference,
    reason: options.decision.reason,
  };
}
