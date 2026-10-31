import { canonicalPath, type ProjectPaths } from "@shadowclone/core";
import { readScopedReferences } from "@shadowclone/profile";
import {
  isOriginBlocked,
  resolveRepository,
  type GitRemoteReader,
} from "@shadowclone/sessions";
import {
  learningRuleSchema,
  type EnvironmentState,
  type LearningRecord,
} from "./types";

export async function migrationRepositories(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
  readonly records: Map<string, LearningRecord>;
  readonly repositories: readonly string[];
  readonly repositoryConsent: boolean;
  readonly blockedOrigins: readonly string[];
  readonly readRemote?: GitRemoteReader;
}) {
  const { records } = options;

  const repositories = [...options.state.repositories];

  for (const directory of options.repositories) {
    const repository = await resolveRepository({
      cwd: directory,
      enabled: options.repositoryConsent,
      readRemote: options.readRemote,
    });

    if (
      isOriginBlocked({ repository, patterns: options.blockedOrigins }) ||
      repository.profileFileName === null ||
      repository.origin.directoryName.startsWith("isolated--")
    ) {
      throw new Error(
        "Migration requires a verified, consented repository identity",
      );
    }

    const registered = {
      directory: canonicalPath(directory),
      originDirectory: repository.origin.directoryName,
      repositoryName: repository.profileFileName,
    };

    if (
      !repositories.some((entry) => entry.directory === registered.directory)
    ) {
      repositories.push(registered);
    }

    const references = await readScopedReferences({
      profileDirectory: options.paths.profileDirectory,
      origin: repository.origin,
      targetRepo: repository.profileFileName,
    });

    for (const { record } of references) {
      const key = `reference:${record.scope}:${record.originDirectory ?? "global"}:${record.repositoryName ?? ""}:${record.key}`;

      if (records.has(key)) {
        continue;
      }

      records.set(key, {
        kind: "context",
        sourceHash: null,
        sourceLocator: record.sourceLocator,
        rule: learningRuleSchema.parse({
          key,
          title: record.title,
          body: record.body,
          section: "workflow",
          source: "user",
          status: "active",
          proposal: null,
          scope: record.scope,
          originDirectory: record.originDirectory,
          repositoryName: record.repositoryName,
          appliesWhen: record.tags,
          evidence: { for: [], against: [] },
          observations: 1,
          sessions: 1,
          lastSeen: record.updatedAt,
          origins: [],
          importReference: null,
        }),
      });
    }
  }

  return repositories;
}
