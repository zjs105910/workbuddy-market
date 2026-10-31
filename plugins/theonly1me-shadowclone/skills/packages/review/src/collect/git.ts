import { runHostCommand } from "@shadowclone/core";

export async function readGit(options: {
  readonly checkout: string;
  readonly arguments: readonly string[];
}): Promise<string> {
  const result = await runHostCommand({
    arguments: ["git", "-c", "core.quotePath=false", ...options.arguments],
    cwd: options.checkout,
  });

  if (result.exitCode !== 0) {
    const [subcommand] = options.arguments;

    throw new Error(
      `git ${subcommand ?? ""} failed: ${result.stderr.trim().slice(0, 300)}`,
    );
  }

  return result.stdout;
}
