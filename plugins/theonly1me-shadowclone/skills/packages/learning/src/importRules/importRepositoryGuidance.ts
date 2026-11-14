import { guidanceImportState } from "./learningState";
import { canonicalPath } from "@shadowclone/core";
import { lstat } from "node:fs/promises";
import type { ProjectPaths } from "@shadowclone/core";
import { createProfileRuleKey } from "@shadowclone/profile";
import type { ProfileRule, ProfileRuleReference } from "@shadowclone/profile";
import {
  resolveRedacted,
  isOriginBlocked,
  resolveRepository,
  type GitRemoteReader,
} from "@shadowclone/sessions";
import { discoverRepositoryGuidance } from "./discovery";
import type { RepositoryGuidanceSource } from "./discovery";
import {
  matchingImportReference,
  mergeImportReference,
  repositoryAliases,
  sourceLocator,
} from "./identity";
import { transformRepositoryGuidance } from "./markdown";
import { isRemovedImport } from "./retirement";
import type {
  ImportIdentity,
  RedactedResolver,
  RepositoryGuidanceImportResult,
  RepositoryRuleLocation,
} from "./types";
import { writeProfile } from "@shadowclone/environment";

function findIdentity(options: {
  readonly identities: readonly ImportIdentity[];
  readonly aliases: readonly string[];
  readonly locator: string;
}): ImportIdentity | null {
  return (
    options.identities.find((identity) =>
      matchingImportReference({
        stored: identity.importReference,
        aliases: options.aliases,
        locator: options.locator,
      }),
    ) ?? null
  );
}

async function resolveSource(options: {
  readonly source: RepositoryGuidanceSource;
  readonly resolveText: RedactedResolver;
}): Promise<string> {
  let byteLength: number;

  try {
    const metadata = await lstat(options.source.filePath);

    byteLength = metadata.isFile() ? metadata.size : -1;
  } catch {
    throw new Error("Repository guidance changed during import");
  }

  if (byteLength !== options.source.byteLength) {
    throw new Error("Repository guidance changed during import");
  }

  const text = await options.resolveText({
    ref: {
      type: "file",
      sourcePath: options.source.filePath,
      byteOffset: 0,
      byteLength,
    },
  });

  if (text.length === 0) {
    throw new Error("Repository guidance changed during import");
  }

  return text;
}

function ruleLocation(options: {
  readonly originDirectory: string;
  readonly repositoryName: string | null;
}): RepositoryRuleLocation {
  return options.repositoryName === null
    ? {
        scope: "org",
        originDirectory: options.originDirectory,
        repositoryName: null,
      }
    : {
        scope: "project",
        originDirectory: options.originDirectory,
        repositoryName: options.repositoryName,
      };
}

export async function importRepositoryGuidance(options: {
  readonly paths: ProjectPaths;
  readonly workingDirectory: string;
  readonly gitMetadataEnabled: boolean;
  readonly blockedOrigins?: readonly string[];
  readonly readRemote?: GitRemoteReader;
  readonly resolveText?: RedactedResolver;
}): Promise<RepositoryGuidanceImportResult> {
  const repository = await resolveRepository({
    cwd: options.workingDirectory,
    enabled: options.gitMetadataEnabled,
    readRemote: options.readRemote,
  });

  if (
    isOriginBlocked({
      repository,
      patterns: options.blockedOrigins ?? [],
    })
  ) {
    throw new Error("Managed policy blocks this repository");
  }

  const imported = await guidanceImportState(options.paths);
  const sources = (
    await discoverRepositoryGuidance(options.workingDirectory)
  ).filter((source) => !imported.owned.has(canonicalPath(source.filePath)));
  const aliases = repositoryAliases({
    workingDirectory: options.workingDirectory,
    repository,
  });
  const { previous, rejections } = imported;
  const identities: readonly ImportIdentity[] = [
    ...previous.filter((entry) => entry.disposition === "present"),
    ...rejections,
  ];
  const currentLocators = new Set(
    sources.map((source) => sourceLocator(source.relativePath)),
  );
  const rules: ProfileRule[] = [];
  const resolveText: RedactedResolver =
    options.resolveText ??
    ((request) =>
      resolveRedacted({ ...request, roots: [options.workingDirectory] }));

  for (const source of sources) {
    const locator = sourceLocator(source.relativePath);
    const identity = findIdentity({ identities, aliases, locator });
    const content = transformRepositoryGuidance({
      source,
      redactedText: await resolveSource({ source, resolveText }),
    });

    if (content === null) {
      continue;
    }

    rules.push({
      key: identity?.key ?? createProfileRuleKey(),
      ...content,
      section: "workflow",
      ...ruleLocation({
        originDirectory: repository.origin.directoryName,
        repositoryName: repository.profileFileName,
      }),
      source: "imported",
      status: "active",
      proposal: null,
      appliesWhen: [],
      evidence: { for: [], against: [] },
      observations: 0,
      lastSeen: "imported",
      sessions: 0,
      origins: [],
      importReference: mergeImportReference({
        stored: identity?.importReference ?? null,
        aliases,
        locator,
      }),
    });
  }

  const retired: ProfileRuleReference[] = previous.flatMap((entry) =>
    isRemovedImport({ entry, aliases, currentLocators })
      ? [{ relativePath: entry.relativePath, key: entry.key }]
      : [],
  );
  const result = await writeProfile({ paths: options.paths, rules, retired });
  const rejectedKeys = new Set(
    (await guidanceImportState(options.paths)).rejections.map(
      (entry) => entry.key,
    ),
  );
  const rejected = rules.filter((rule) => rejectedKeys.has(rule.key)).length;

  return {
    imported: rules.length - result.preserved - rejected,
    preserved: result.preserved,
    rejected,
    retired: retired.length,
  };
}
