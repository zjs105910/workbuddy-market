import path from "node:path";
import {
  readEffectiveConfig,
  fingerprint,
  readLocalText,
  acquireLocalLock,
} from "@shadowclone/core";
import { compileContext } from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";
import {
  discoverSkills,
  registerPortableSkill,
  isPluginCache,
  readMaintenanceState,
  skillTarget,
  writeMaintenanceState,
} from "@shadowclone/skills";

export async function inspectSkillLibrary(options: {
  readonly paths: ProjectPaths;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
}) {
  const { config } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? options.paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!config.sources["skill-library"]) {
    throw new Error(
      "Skill library access is disabled; run skills configure first",
    );
  }

  const state = await readMaintenanceState(options.paths);
  const roots = [];

  for (const root of state.roots) {
    if (!root.enabled) {
      continue;
    }

    if (
      (await compileContext({
        ...options,
        cwd: root.cwd,
        scope: root.scope === "global" ? "global" : "combined",
      })) !== null
    ) {
      roots.push(root);
    }
  }

  return discoverSkills(roots);
}

export async function adoptSkill(options: {
  readonly paths: ProjectPaths;
  readonly id: string;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
}): Promise<void> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "skills-worker.db"),
  );

  if (!lock) {
    throw new Error("Another skill update is running");
  }

  try {
    const discovered = await inspectSkillLibrary(options);
    const skill = discovered.skills.find((entry) => entry.id === options.id);

    if (skill?.root.owner !== "user") {
      throw new Error("Only a discovered user-owned skill can be adopted");
    }

    if (isPluginCache(skill.root.directory)) {
      throw new Error("Installed plugin caches cannot be adopted");
    }

    const sourcePath = skillTarget({
      directory: skill.root.directory,
      relativePath: skill.relativePath,
    });

    const portable = await registerPortableSkill({
      paths: options.paths,
      name: skill.name,
      sourceDirectory: path.dirname(sourcePath),
      managedBy: "adopted",
    });

    const canonicalRelativePath = `${skill.name}/SKILL.md`;
    const canonicalPath = skillTarget({
      directory: path.dirname(portable.sourceDirectory),
      relativePath: canonicalRelativePath,
    });
    const canonicalText = await readLocalText(canonicalPath);

    if (canonicalText === null) {
      throw new Error("Portable skill installation did not produce SKILL.md");
    }

    const canonicalId = fingerprint(canonicalPath);
    const canonicalRootId = fingerprint(path.dirname(portable.sourceDirectory));
    const state = await readMaintenanceState(options.paths);

    await writeMaintenanceState({
      paths: options.paths,
      state: {
        ...state,
        tracked: [
          ...state.tracked.filter(
            (entry) => entry.id !== skill.id && entry.id !== canonicalId,
          ),
          {
            id: canonicalId,
            rootId: canonicalRootId,
            relativePath: canonicalRelativePath,
            fingerprint: fingerprint(canonicalText),
            automatic: true,
            kind: "amend",
          },
        ],
        assessed: Object.fromEntries(
          Object.entries(state.assessed).filter(
            ([id]) => id !== skill.id && id !== canonicalId,
          ),
        ),
      },
    });
  } finally {
    lock.release();
  }
}
