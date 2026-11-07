import type { ProjectPaths } from "@shadowclone/core";
import { readLocalText, readLocalFile, fingerprint, acquireLocalLock } from "@shadowclone/core";
import path from "node:path";
import {
  environmentFile,
  readEnvironment,
  readRedactedEnvironment,
  renderEnvironment,
} from "./store";
import { belongsToScope, learningScopes } from "./scope";
import { recordFingerprint } from "./records";
import { nativePublication } from "./native";
import { publishEnvironmentRevision } from "./revision";

export async function activateEnvironment(
  paths: ProjectPaths,
): Promise<string | null> {
  const lock = await acquireLocalLock(
    path.join(paths.shadowcloneDirectory, "environment-write.db"),
  );

  if (!lock) {
    throw new Error("Another learning update is running");
  }

  try {
    const state = await readEnvironment(paths);

    if (state === null) {
      throw new Error("Prepare the skills migration first");
    }

    const scopes = learningScopes({ paths, state });
    const records = (await readRedactedEnvironment(paths))?.records ?? [];

    const pending = records.filter(
      (record) =>
        record.rule.status === "active" &&
        record.rule.source !== "imported" &&
        scopes.some(
          (scope) =>
            belongsToScope({ record, scope }) &&
            !state.dispositions.some(
              (entry) =>
                entry.key === record.rule.key &&
                entry.scope === scope.key &&
                entry.inputFingerprint === recordFingerprint(record) &&
                entry.status !== "pending",
            ),
        ),
    );

    if (pending.length > 0) {
      throw new Error(
        `${pending.length} applicable learning(s) still need publication or a reviewed disposition`,
      );
    }

    if (
      !state.artifacts.some(
        (artifact) => artifact.name === "shadowclone-baseline",
      )
    ) {
      throw new Error("The mandatory baseline skill has not been published");
    }

    for (const artifact of state.artifacts.filter(
      (entry) => entry.kind !== "instructions",
    )) {
      const current = await readLocalFile(artifact);

      if (current === null || fingerprint(current) !== artifact.fingerprint) {
        throw new Error(
          "A published skill or resource changed before activation; reconcile it first",
        );
      }
    }

    for (const disposition of state.dispositions.filter(
      (entry) => entry.status === "covered",
    )) {
      for (const filePath of disposition.destinations) {
        const current = await readLocalText(filePath);

        if (
          current === null ||
          fingerprint(current) !== disposition.fingerprints?.[filePath]
        ) {
          throw new Error(
            "An existing skill used as coverage changed before activation; retry its learning",
          );
        }
      }
    }

    const publication = await nativePublication({
      paths,
      state: { ...state, phase: "active" },
    });
    const filePath = environmentFile(paths);

    return publishEnvironmentRevision({
      paths,
      updates: [
        ...publication.updates,
        {
          filePath,
          previous: await readLocalText(filePath),
          next: renderEnvironment(publication.state),
        },
      ],
    });
  } finally {
    lock.release();
  }
}
