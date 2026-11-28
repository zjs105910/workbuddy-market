import path from "node:path";
import { readLocalText, replaceLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { materializeSnapshot } from "@shadowclone/redact";
import { environmentSchema, type EnvironmentState } from "./types";

export function environmentFile(paths: ProjectPaths): string {
  return path.join(paths.shadowcloneDirectory, "environment.json");
}

export function renderEnvironment(state: EnvironmentState): string {
  return `${JSON.stringify(environmentSchema.parse(state), null, 2)}\n`;
}

export async function readEnvironment(
  paths: ProjectPaths,
): Promise<EnvironmentState | null> {
  const text = await readLocalText(environmentFile(paths));

  if (text === null) {
    return null;
  }

  try {
    return environmentSchema.parse(JSON.parse(text));
  } catch {
    throw new Error(
      "Invalid learning environment; restore its revision before continuing",
    );
  }
}

export async function readRedactedEnvironment(
  paths: ProjectPaths,
): Promise<EnvironmentState | null> {
  const snapshot = await materializeSnapshot({
    filePath: environmentFile(paths),
    roots: [paths.shadowcloneDirectory],
    maximumBytes: 4_000_000,
    parse: (text) => environmentSchema.parse(JSON.parse(text)),
  });

  if (snapshot === null) {
    return null;
  }

  const redacted = environmentSchema.parse(JSON.parse(snapshot.redacted));
  const original = snapshot.parsed;

  return environmentSchema.parse({
    ...redacted,
    repositories: original.repositories,
    baselineDirectory: original.baselineDirectory,
    builds: redacted.builds.map((build, index) => ({
      ...build,
      directory: original.builds[index]?.directory ?? build.directory,
      id: original.builds[index]?.id ?? build.id,
    })),
    records: redacted.records.map((record, index) => {
      const identity = original.records[index]?.rule;

      return identity
        ? {
            ...record,
            rule: {
              ...record.rule,
              key: identity.key,
              scope: identity.scope,
              originDirectory: identity.originDirectory,
              repositoryName: identity.repositoryName,
            },
          }
        : record;
    }),
    artifacts: redacted.artifacts.map((artifact, index) => {
      const identity = original.artifacts[index];

      return identity
        ? {
            ...artifact,
            filePath: identity.filePath,
            scope: identity.scope,
            name: identity.name,
            fingerprint: identity.fingerprint,
          }
        : artifact;
    }),
    dispositions: redacted.dispositions.map((disposition, index) => ({
      ...disposition,
      scope: original.dispositions[index]?.scope,
      key: original.dispositions[index]?.key ?? disposition.key,
      inputFingerprint:
        original.dispositions[index]?.inputFingerprint ??
        disposition.inputFingerprint,
    })),
    facts: redacted.facts.map((fact, index) => ({
      ...fact,
      scope: original.facts[index]?.scope ?? fact.scope,
    })),
  });
}

export async function writeEnvironment(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
}): Promise<void> {
  const filePath = environmentFile(options.paths);

  await replaceLocalText({
    filePath,
    previous: await readLocalText(filePath),
    next: renderEnvironment(options.state),
  });
}
