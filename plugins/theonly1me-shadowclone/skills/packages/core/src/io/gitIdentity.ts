import { runProcess } from "./process";

export async function gitIdentityArguments(options: {
  readonly cwd: string;
  readonly environment: Readonly<Record<string, string | undefined>>;
}): Promise<readonly string[]> {
  const arguments_: string[] = [];

  for (const key of ["user.name", "user.email"]) {
    const result = await runProcess({
      arguments: ["git", "config", "--get", key],
      cwd: options.cwd,
      environment: { ...options.environment, GIT_CONFIG_GLOBAL: undefined },
      timeoutMilliseconds: 10_000,
      maximumOutputBytes: 4096,
    });

    const value = result.stdout.trim();

    if (result.exitCode === 0 && value.length > 0) {
      arguments_.push("-c", `${key}=${value}`);
    }
  }

  return arguments_;
}
