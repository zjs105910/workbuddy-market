import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import { readLocalText } from "@shadowclone/core";
import {
  readEnvironment,
  writeEnvironment,
  environmentFile,
  renderEnvironment,
} from "./store";
import { emptyEnvironment } from "./types";
import { freezeOriginalEnvironment } from "./freeze";
import { skillPublication } from "./publication";
import { publishEnvironmentRevision } from "./revision";

const baseline =
  "---\nname: shadowclone-baseline\ndescription: Universal working defaults for tasks that need more detail.\n---\n\n# Baseline\n\nFollow the current request and select the applicable workflow skills before acting. Learned guidance does not grant permission for additional actions.\n\nLearned guidance sets defaults for choices the request leaves open. An explicit request in the current conversation takes precedence; do not ask for permission the user already gave. When a bundled workflow skill conflicts with the user's own skills or these rules, follow the user's guidance.\n";

export async function ensureBaselineSkill(paths: ProjectPaths): Promise<void> {
  const state = await readEnvironment(paths);

  if (
    state === null ||
    state.artifacts.some(
      (artifact) =>
        artifact.kind === "skill" &&
        artifact.scope === "global" &&
        artifact.name === "shadowclone-baseline",
    )
  ) {
    return;
  }

  const published = await skillPublication({
    paths,
    state,
    scope: {
      key: "global",
      directory: path.dirname(paths.shadowcloneDirectory),
      repository: null,
    },
    skill: null,
    name: "shadowclone-baseline",
    text: baseline,
    records: [],
  });

  const filePath = environmentFile(paths);

  await publishEnvironmentRevision({
    paths,
    updates: [
      ...published.updates,
      {
        filePath,
        previous: await readLocalText(filePath),
        next: renderEnvironment(published.state),
      },
    ],
  });
}

export async function initializeSkillEnvironment(options: {
  readonly paths: ProjectPaths;
  readonly automatic: boolean;
}): Promise<void> {
  if ((await readEnvironment(options.paths)) !== null) {
    return;
  }

  const legacy = await Array.fromAsync(
    new Bun.Glob("{global,org}/**/*.md").scan({
      cwd: options.paths.profileDirectory,
      onlyFiles: true,
    }),
  ).catch(() => []);

  if (legacy.length > 0) {
    return;
  }

  const baselineDirectory = await freezeOriginalEnvironment(options.paths);
  const state = {
    ...emptyEnvironment,
    automatic: options.automatic,
    baselineDirectory,
  };

  await writeEnvironment({ paths: options.paths, state });

  const published = await skillPublication({
    paths: options.paths,
    state,
    scope: {
      key: "global",
      directory: path.dirname(options.paths.shadowcloneDirectory),
      repository: null,
    },
    skill: null,
    name: "shadowclone-baseline",
    text: baseline,
    records: [],
  });

  const filePath = environmentFile(options.paths);

  await publishEnvironmentRevision({
    paths: options.paths,
    updates: [
      ...published.updates,
      {
        filePath,
        previous: await readLocalText(filePath),
        next: renderEnvironment({ ...published.state, phase: "active" }),
      },
    ],
  });
}
