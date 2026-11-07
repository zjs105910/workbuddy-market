import type { ProjectPaths } from "@shadowclone/core";
import { findProfileRule, readProfileFiles } from "./files";
import type { ProfileFile } from "./files";
import { profileRulePath } from "./render";
import { mergeProfileImportReference } from "./importReference";
import {
  readGeneratedProfileState,
  profileRejectionFromState,
  readProfileRejections,
} from "./state";
import type { GeneratedProfileStateEntry, ProfileRejection } from "./state";
import type {
  ExistingProfileRule,
  ProfileRule,
  ProfileRuleReference,
} from "./types";

export type PreparedProfileWrite = {
  readonly incomingRules: readonly ProfileRule[];
  readonly incoming: ReadonlyMap<string, ProfileRule>;
  readonly previousEntries: readonly GeneratedProfileStateEntry[];
  readonly rejections: Map<string, ProfileRejection>;
  readonly retired: Map<string, GeneratedProfileStateEntry>;
  readonly files: readonly ProfileFile[];
  readonly pinned: ReadonlySet<string>;
};

export function generatedProfileEntry(options: {
  readonly relativePath: string;
  readonly rule: ProfileRule | ExistingProfileRule;
  readonly disposition?: GeneratedProfileStateEntry["disposition"];
}): GeneratedProfileStateEntry {
  return {
    relativePath: options.relativePath,
    key: options.rule.key,
    title: options.rule.title,
    body: options.rule.body,
    source: options.rule.source,
    importReference: options.rule.importReference,
    disposition: options.disposition ?? "present",
  };
}

function retiredEntry(options: {
  readonly reference: ProfileRuleReference;
  readonly incoming: ReadonlyMap<string, ProfileRule>;
  readonly files: readonly ProfileFile[];
  readonly previous: ReadonlyMap<string, GeneratedProfileStateEntry>;
}): GeneratedProfileStateEntry {
  const incoming = options.incoming.get(options.reference.key);

  if (incoming) {
    return generatedProfileEntry({
      relativePath: options.reference.relativePath,
      rule: incoming,
      disposition: "retired",
    });
  }

  const existing = findProfileRule(options.files, options.reference.key);

  if (existing) {
    return generatedProfileEntry({
      relativePath: existing.relativePath,
      rule: existing.rule,
      disposition: "retired",
    });
  }

  const previous = options.previous.get(options.reference.key);

  return previous
    ? { ...previous, disposition: "retired" }
    : {
        ...options.reference,
        title: null,
        body: null,
        source: null,
        importReference: null,
        disposition: "retired",
      };
}

export async function prepareProfileWrite(options: {
  readonly paths: ProjectPaths;
  readonly rules: readonly ProfileRule[];
  readonly retiredReferences: readonly ProfileRuleReference[];
}): Promise<PreparedProfileWrite> {
  const incomingRules = [
    ...new Map(options.rules.map((rule) => [rule.key, rule])).values(),
  ];
  const incoming = new Map(incomingRules.map((rule) => [rule.key, rule]));
  const previousEntries = await readGeneratedProfileState(
    options.paths.profileManifestFile,
  );
  const previous = new Map(previousEntries.map((entry) => [entry.key, entry]));
  const rejections = new Map(
    (await readProfileRejections(options.paths.rejectedProfileFile)).map(
      (entry) => [entry.key, entry],
    ),
  );
  const retired = new Map(
    previousEntries
      .filter((entry) => entry.disposition === "retired")
      .map((entry) => [entry.key, entry]),
  );

  for (const rule of incomingRules) {
    const rejection = rejections.get(rule.key);

    if (rejection?.importReference && rule.importReference) {
      rejections.set(rule.key, {
        ...rejection,
        importReference: mergeProfileImportReference({
          stored: rejection.importReference,
          incoming: rule.importReference,
        }),
      });
    }
  }

  const relativePaths = new Set([
    ...incomingRules.map(profileRulePath),
    ...previousEntries.map((entry) => entry.relativePath),
    ...options.retiredReferences.map((entry) => entry.relativePath),
  ]);
  const files = await readProfileFiles({
    profileDirectory: options.paths.profileDirectory,
    relativePaths: [...relativePaths],
  });
  const existingKeys = new Set(
    files.flatMap((file) =>
      file.blocks.flatMap((block) => (block.key === null ? [] : [block.key])),
    ),
  );

  for (const entry of previousEntries) {
    if (
      entry.disposition === "present" &&
      incoming.has(entry.key) &&
      !existingKeys.has(entry.key)
    ) {
      rejections.set(entry.key, profileRejectionFromState(entry));
    }
  }

  for (const reference of options.retiredReferences) {
    retired.set(
      reference.key,
      retiredEntry({ reference, incoming, files, previous }),
    );
  }

  const pinned = new Set(
    files.flatMap((file) =>
      file.blocks.flatMap((block) =>
        block.key !== null && (block.edited || block.source === "user")
          ? [block.key]
          : [],
      ),
    ),
  );

  return {
    incomingRules,
    incoming,
    previousEntries,
    rejections,
    retired,
    files,
    pinned,
  };
}
