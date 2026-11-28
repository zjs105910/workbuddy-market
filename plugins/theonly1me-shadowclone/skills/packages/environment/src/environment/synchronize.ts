import path from "node:path";
import { fingerprint, readLocalText } from "@shadowclone/core";
import type { FileUpdate } from "@shadowclone/changes";
import type { ProjectPaths } from "@shadowclone/core";
import type { EnvironmentState } from "./types";
import { learningScopes } from "./scope";
import { skillPublication } from "./publication";
import { materializeSnapshot } from "@shadowclone/redact";
import { parseSkillDocument } from "@shadowclone/skills";
import { validateRouting } from "./routingValidation";
import { pendingLearningState } from "./learningDisposition";

export async function synchronizePublishedSkills(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
}): Promise<{
  readonly state: EnvironmentState;
  readonly updates: readonly FileUpdate[];
  readonly routingBlocked: boolean;
}> {
  let state = options.state;
  const updates: FileUpdate[] = [];
  let routingBlocked = false;
  const groups = Map.groupBy(
    state.artifacts.filter((artifact) => artifact.kind === "skill" && !artifact.buildId),
    (artifact) => `${artifact.scope}/${artifact.name}`,
  );

  for (const artifacts of groups.values()) {
    const current = await Promise.all(
      artifacts.map(async (artifact) => ({
        artifact,
        text: await readLocalText(artifact.filePath),
      })),
    );

    const changed = current.filter(
      (entry) =>
        entry.text !== null &&
        fingerprint(entry.text) !== entry.artifact.fingerprint,
    );

    if (new Set(changed.map(({ text }) => text)).size > 1) {
      throw new Error(
        "Maintained skill copies have divergent edits; all versions were preserved",
      );
    }

    const authority = changed[0] ?? current.find(({ text }) => text !== null);

    if (!authority?.text) {
      throw new Error(
        "Every copy of a maintained skill is missing; restore a revision first",
      );
    }

    const { artifact, text } = authority;
    const document = parseSkillDocument(text);

    if (
      changed.length === 0 &&
      current.every(({ text, artifact }) =>
        text !== null && artifact.description === document.metadata.description,
      )
    ) {
      continue;
    }

    const scope = learningScopes(options).find(
      (entry) => entry.key === artifact.scope,
    );

    if (!scope) {
      throw new Error("Maintained skill scope is unavailable");
    }

    const directory = path.dirname(path.dirname(artifact.filePath));

    const snapshot = await materializeSnapshot({
      filePath: artifact.filePath,
      roots: [directory],
      maximumBytes: 48_000,
      parse: () => null,
    });

    if (!snapshot) {
      throw new Error("Maintained skill is unavailable");
    }

    const publication = await skillPublication({
      paths: options.paths,
      state,
      scope,
      name: artifact.name,
      text,
      records: [],
      skill: {
        id: fingerprint(artifact.filePath),
        name: artifact.name,
        description: document.metadata.description,
        raw: text,
        redacted: snapshot.redacted,
        body: snapshot.redacted,
        fingerprint: fingerprint(text),
        relativePath: path.relative(directory, artifact.filePath),
        root: {
          id: fingerprint(directory),
          directory,
          cwd: scope.directory,
          scope: scope.repository ? "repository" : "global",
          owner: "user",
          destination: directory,
          enabled: true,
        },
      },
    });

    try {
      validateRouting({ paths: options.paths, state: publication.state });
    } catch {
      routingBlocked = true;
      const keys = new Set(artifacts.flatMap((entry) => entry.learningKeys));
      const records = state.records.filter(({ rule }) => keys.has(rule.key));

      if (records.length === 0) {
        throw new Error("Native routing exceeds 4 KiB. Review and shorten the validated skill descriptions before synchronizing.");
      }

      state = pendingLearningState({
        state, scope, records, keys,
        reasons: records.map(({ rule }) => ({
          key: rule.key,
          reason: "Native routing exceeds 4 KiB. Shorten the skill description, synchronize, and retry this learning. Existing routing was preserved.",
        })),
        destinations: artifacts.map((entry) => entry.filePath),
      });
      continue;
    }

    state = publication.state;
    updates.push(...publication.updates);
  }

  return { state, updates, routingBlocked };
}
