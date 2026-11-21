import { runProcess } from "@shadowclone/core";

export async function git(options: {
  readonly clone: string;
  readonly arguments: readonly string[];
  readonly environment?: Readonly<Record<string, string>>;
}): Promise<string> {
  const result = await runProcess({
    arguments: ["git", ...options.arguments],
    cwd: options.clone,
    environment: { ...process.env, ...options.environment },
    timeoutMilliseconds: 600_000,
  });

  if (result.exitCode !== 0) {
    throw new Error(`git ${options.arguments[0] ?? ""} failed: ${result.stderr.trim().slice(0, 300)}`);
  }

  return result.stdout.trim();
}
