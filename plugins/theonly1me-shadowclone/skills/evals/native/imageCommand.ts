import { runProcess } from "@shadowclone/core";
import { NativeInfrastructureError, type NativeDiagnostic } from "./diagnostics";

type ImageRun = (options: {
  readonly arguments: readonly string[];
  readonly directory: string;
}) => Promise<Awaited<ReturnType<typeof runProcess>>>;

const imageAttempts = 3;

const runHdiutil: ImageRun = (options) =>
  runProcess({
    arguments: ["hdiutil", ...options.arguments],
    cwd: options.directory,
    environment: process.env,
    timeoutMilliseconds: 60_000,
    maximumOutputBytes: 4096,
  });

export async function imageCommand(options: {
  readonly arguments: readonly string[];
  readonly directory: string;
  readonly stage: NativeDiagnostic["stage"];
  readonly forceOnLastAttempt?: boolean;
  readonly run?: ImageRun;
  readonly pauseMilliseconds?: number;
}): Promise<void> {
  const run = options.run ?? runHdiutil;
  const failures: string[] = [];

  for (let attempt = 1; attempt <= imageAttempts; attempt += 1) {
    const isLastAttempt = attempt === imageAttempts;
    const arguments_ =
      options.forceOnLastAttempt && isLastAttempt
        ? [...options.arguments, "-force"]
        : options.arguments;
    const result = await run({ arguments: arguments_, directory: options.directory });

    if (result.exitCode === 0) {
      return;
    }

    failures.push(
      `attempt ${attempt}: hdiutil exit ${result.exitCode}\n${result.stdout}\n${result.stderr}`,
    );

    if (!isLastAttempt) {
      await Bun.sleep((options.pauseMilliseconds ?? 1_000) * attempt);
    }
  }

  throw new NativeInfrastructureError({
    stage: options.stage,
    confirmedInfrastructure: true,
    message: "Read-only workspace mount failed",
    details: failures.join("\n"),
  });
}
