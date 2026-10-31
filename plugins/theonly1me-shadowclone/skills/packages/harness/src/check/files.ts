import { runCommand, type CommandRunner } from "@shadowclone/core";

const skippedDirectories = new Set([
  ".git",
  "node_modules",
  "dist",
  "build",
  "out",
  "coverage",
  ".venv",
  "venv",
  "target",
  "__pycache__",
]);
const maximumFiles = 20_000;

async function gitLines(options: {
  readonly runner: CommandRunner;
  readonly root: string;
  readonly arguments: readonly string[];
}): Promise<readonly string[] | null> {
  const result = await options.runner({
    command: ["git", ...options.arguments],
    cwd: options.root,
  });

  return result.exitCode === 0
    ? result.stdout
        .split("\n")
        .map((line) => line.trim())
        .filter((line) => line.length > 0)
    : null;
}

async function scannedFiles(root: string): Promise<readonly string[]> {
  const files: string[] = [];

  for await (const file of new Bun.Glob("**/*").scan({
    cwd: root,
    onlyFiles: true,
    dot: true,
    followSymlinks: false,
  })) {
    if (file.split("/").some((segment) => skippedDirectories.has(segment))) {
      continue;
    }

    files.push(file);

    if (files.length > maximumFiles) {
      throw new Error("The repository has too many files to check");
    }
  }

  return files;
}

export async function listCheckFiles(options: {
  readonly root: string;
  readonly changed: boolean;
  readonly runner?: CommandRunner;
}): Promise<readonly string[]> {
  const runner = options.runner ?? runCommand;
  const untracked = await gitLines({
    runner,
    root: options.root,
    arguments: ["ls-files", "--others", "--exclude-standard"],
  });

  if (untracked === null) {
    return [...(await scannedFiles(options.root))].sort();
  }

  const tracked = options.changed
    ? ((await gitLines({
        runner,
        root: options.root,
        arguments: ["diff", "--name-only", "--diff-filter=d", "HEAD"],
      })) ??
      (await gitLines({ runner, root: options.root, arguments: ["ls-files"] })))
    : await gitLines({ runner, root: options.root, arguments: ["ls-files"] });
  const files = [...new Set([...(tracked ?? []), ...untracked])];

  if (files.length > maximumFiles) {
    throw new Error("The repository has too many files to check");
  }

  return files
    .filter(
      (file) =>
        !file.split("/").some((segment) => skippedDirectories.has(segment)),
    )
    .sort();
}
