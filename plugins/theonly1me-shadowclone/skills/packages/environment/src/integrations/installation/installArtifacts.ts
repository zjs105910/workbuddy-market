import { artifactIsOwned } from "./artifactOwnership";
import { runHostCommand } from "@shadowclone/core";
import type { Installation } from "./installState";
import { mkdir, rm, rmdir } from "node:fs/promises";
import path from "node:path";
import { resolveArtifactPath } from "./installTarget";
import type { InstalledArtifact } from "./installState";

export { artifactRelativePaths, artifactExcludePatterns } from "./installPaths";
import { artifactRelativePaths, artifactExcludePatterns } from "./installPaths";
import { integrationTargets } from "../targets";
import { integrationAgentSchema } from "../types";

export function integrationExcludePattern(relativePath: string): string {
  return `/${relativePath}`;
}

const ownedExcludePatterns = new Set([
  ...Object.values(artifactExcludePatterns),
  ...integrationAgentSchema.options.flatMap((agent) =>
    integrationTargets({
      agent,
      scope: "repository",
      directory: "/",
      userDirectory: "/",
      codexInstructions: "AGENTS.override.md",
    }).map(({ relativePath }) => integrationExcludePattern(relativePath)),
  ),
]);

const ownedLeafDirectory = path.join(".claude", "skills", "shadowclone");

async function gitExcludePath(cwd: string): Promise<string | null> {
  const { exitCode, stdout } = await runHostCommand({
    arguments: ["git", "rev-parse", "--git-path", "info/exclude"],
    cwd,
  });

  if (exitCode !== 0) {
    return null;
  }

  const relativeExclude = stdout.trim();

  if (relativeExclude.length === 0) {
    return null;
  }

  const absolute = path.resolve(cwd, relativeExclude);

  if (!absolute.startsWith(`${path.resolve(cwd)}${path.sep}`)) {
    return null;
  }

  return resolveArtifactPath({
    root: path.resolve(cwd),
    relativePath: path.relative(cwd, absolute),
  });
}

export async function addGitExcludes(options: {
  readonly cwd: string;
  readonly patterns: readonly string[];
}): Promise<readonly string[]> {
  const excludePath = await gitExcludePath(options.cwd);

  if (excludePath === null) {
    return [];
  }

  const excludeFile = Bun.file(excludePath);
  const existing = (await excludeFile.exists()) ? await excludeFile.text() : "";
  const lines = existing.split("\n").map((line) => line.trim());
  const missing = options.patterns
    .filter((pattern) => ownedExcludePatterns.has(pattern))
    .filter((pattern) => !lines.includes(pattern));

  if (missing.length === 0) {
    return [];
  }

  await mkdir(path.dirname(excludePath), { recursive: true });

  const prefix =
    existing.length > 0 && !existing.endsWith("\n")
      ? `${existing}\n`
      : existing;

  await Bun.write(excludePath, `${prefix}${missing.join("\n")}\n`);

  return missing;
}

export async function removeGitExcludes(options: {
  readonly cwd: string;
  readonly patterns: readonly string[];
}): Promise<void> {
  if (options.patterns.length === 0) {
    return;
  }

  const excludePath = await gitExcludePath(options.cwd);

  if (excludePath === null) {
    return;
  }

  const excludeFile = Bun.file(excludePath);

  if (!(await excludeFile.exists())) {
    return;
  }

  const existing = await excludeFile.text();
  const kept = existing
    .split("\n")
    .filter(
      (line) =>
        !(
          ownedExcludePatterns.has(line.trim()) &&
          options.patterns.includes(line.trim())
        ),
    );
  const trailing = existing.endsWith("\n") && kept.at(-1) === "" ? "" : "\n";

  await Bun.write(excludePath, `${kept.join("\n")}${trailing}`);
}

export async function removeArtifacts(options: {
  readonly directory: string;
  readonly artifacts: readonly InstalledArtifact[];
  readonly installation?: Installation | null;
}): Promise<number> {
  let removed = 0;

  for (const artifact of options.artifacts) {
    const artifactPath = await resolveArtifactPath({
      root: options.directory,
      relativePath: artifactRelativePaths[artifact],
    });

    if (
      artifactPath === null ||
      !(await artifactIsOwned({
        directory: options.directory,
        artifact,
        installation: options.installation,
      }))
    ) {
      continue;
    }

    if (await Bun.file(artifactPath).exists()) {
      removed += 1;
    }

    await rm(artifactPath, { force: true });
  }

  const leafDirectory = await resolveArtifactPath({
    root: options.directory,
    relativePath: ownedLeafDirectory,
  });

  if (leafDirectory !== null) {
    await rmdir(leafDirectory).catch(() => undefined);
  }

  return removed;
}
