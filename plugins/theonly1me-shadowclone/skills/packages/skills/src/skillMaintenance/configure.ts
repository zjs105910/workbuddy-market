import path from "node:path";
import {
  readConfig,
  readEffectiveConfig,
  setSourceEnabled,
  writeConfig,
  fingerprint,
  acquireLocalLock,
  canonicalPath,
  projectPaths,
  type ProjectPaths,
} from "@shadowclone/core";
import {
  isPluginCache,
  readMaintenanceState,
  writeMaintenanceState,
} from "./state";
import type { SkillRoot } from "./types";

export function standardSkillRoots(options: {
  readonly paths: ProjectPaths;
  readonly cwd: string;
  readonly scope: SkillRoot["scope"];
}): readonly SkillRoot[] {
  const homeDirectory = path.dirname(options.paths.shadowcloneDirectory);
  const cwd = canonicalPath(options.cwd);
  const base = options.scope === "global" ? homeDirectory : cwd;
  const codexHome = path.dirname(options.paths.codexSessionsDirectory);

  const roots = [".claude/skills", ".agents/skills", ".cursor/skills"].map(
    (relative) => ({
      directory: canonicalPath(path.join(base, relative)),
      destination: canonicalPath(path.join(base, relative)),
      owner: "user" as const,
    }),
  );

  if (options.scope === "global") {
    const plugins: readonly {
      readonly directory: string;
      readonly destination: string;
      readonly owner: "third-party";
    }[] = [
      {
        directory: path.join(homeDirectory, ".claude/plugins/cache"),
        destination: path.join(homeDirectory, ".claude/skills"),
        owner: "third-party",
      },
      {
        directory: path.join(codexHome, "plugins/cache"),
        destination: path.join(homeDirectory, ".agents/skills"),
        owner: "third-party",
      },
      {
        directory: path.join(homeDirectory, ".cursor/plugins/cache"),
        destination: path.join(homeDirectory, ".cursor/skills"),
        owner: "third-party",
      },
    ];

    return [...roots, ...plugins].map((root) => ({
      ...root,
      id: fingerprint(root.directory),
      cwd: options.scope === "global" ? homeDirectory : cwd,
      scope: options.scope,
      enabled: true,
    }));
  }

  return roots.map((root) => ({
    ...root,
    id: fingerprint(root.directory),
    cwd,
    scope: options.scope,
    enabled: true,
  }));
}

export async function configureSkillMaintenance(options: {
  readonly scope: SkillRoot["scope"];
  readonly cwd?: string;
  readonly paths?: ProjectPaths;
  readonly managedConfigPath?: string | null;
  readonly rootDirectory?: string;
  readonly thirdParty?: boolean;
}): Promise<number> {
  const paths = options.paths ?? projectPaths;

  const { policy } = await readEffectiveConfig({
    configPath: paths.configFile,
    managedConfigPath:
      options.managedConfigPath === undefined
        ? paths.managedConfigFile
        : options.managedConfigPath,
  });

  if (!policy.enabled || !policy.allowedSources.includes("skill-library")) {
    throw new Error("Managed policy blocks skill library access");
  }

  const lock = await acquireLocalLock(
    path.join(paths.shadowcloneDirectory, "skills-worker.db"),
  );

  if (!lock) {
    throw new Error("Another skill update is running");
  }

  try {
    const state = await readMaintenanceState(paths);
    const directory = options.rootDirectory
      ? canonicalPath(options.rootDirectory)
      : null;
    const homeDirectory = path.dirname(paths.shadowcloneDirectory);
    const thirdParty =
      options.thirdParty || (directory !== null && isPluginCache(directory));

    const selected: readonly SkillRoot[] = directory
      ? [
          {
            id: fingerprint(directory),
            directory,
            cwd:
              options.scope === "global"
                ? homeDirectory
                : canonicalPath(options.cwd ?? process.cwd()),
            scope: options.scope,
            enabled: true,
            owner: thirdParty ? "third-party" : "user",
            destination: thirdParty
              ? path.join(
                  options.scope === "global"
                    ? homeDirectory
                    : canonicalPath(options.cwd ?? process.cwd()),
                  ".agents/skills",
                )
              : directory,
          },
        ]
      : standardSkillRoots({
          paths,
          cwd: options.cwd ?? process.cwd(),
          scope: options.scope,
        });

    const roots = [
      ...new Map(
        [...state.roots, ...selected].map((root) => [root.id, root]),
      ).values(),
    ];

    await writeMaintenanceState({ paths, state: { ...state, roots } });

    const config = await readConfig({ configPath: paths.configFile });

    await writeConfig({
      configPath: paths.configFile,
      config: setSourceEnabled({
        config,
        source: "skill-library",
        enabled: true,
      }),
    });

    return selected.length;
  } finally {
    lock.release();
  }
}
