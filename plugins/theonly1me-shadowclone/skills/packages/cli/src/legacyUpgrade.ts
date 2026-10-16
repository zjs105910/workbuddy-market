import { rm } from "node:fs/promises";
import path from "node:path";
import {
  artifactRelativePaths,
  compileContext,
  findInstallation,
  readInstallations,
  removeGitExcludes,
  writeInstallations,
} from "@shadowclone/environment";
import { canonicalPath, projectPaths, type ProjectPaths } from "@shadowclone/core";
import { renderAgent } from "@shadowclone/profile";

export async function removeUneditedLegacySubagent(
  options: { readonly cwd?: string; readonly paths?: ProjectPaths } = {},
): Promise<boolean> {
  const cwd = canonicalPath(options.cwd ?? process.cwd());
  const paths = options.paths ?? projectPaths;
  const state = await readInstallations(paths.installationsFile);
  const installation = findInstallation({ state, directory: cwd });

  if (!installation?.artifacts.includes("agent")) {
    return false;
  }

  const filePath = path.join(cwd, artifactRelativePaths.agent);
  const file = Bun.file(filePath);

  if (!(await file.exists())) {
    return false;
  }

  const profile = await compileContext({ paths, cwd });

  if (profile === null || (await file.text()) !== renderAgent({ profile })) {
    return false;
  }

  await rm(filePath);
  await removeGitExcludes({
    cwd,
    patterns: [".claude/agents/shadowclone.md"],
  });

  const artifacts = installation.artifacts.filter(
    (artifact) => artifact !== "agent",
  );
  const updatedInstallations = state.installations.flatMap((entry) => {
    if (entry.directory !== cwd) {
      return [entry];
    }

    return artifacts.length === 0
      ? []
      : [
          {
            ...entry,
            artifacts,
            excludes: entry.excludes.filter(
              (exclude) => exclude !== ".claude/agents/shadowclone.md",
            ),
          },
        ];
  });

  await writeInstallations({
    filePath: paths.installationsFile,
    state: { version: 1, installations: updatedInstallations },
  });

  return true;
}
