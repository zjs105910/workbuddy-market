import { mkdir, realpath } from "node:fs/promises";
import path from "node:path";
import os from "node:os";
import { runProcess } from "@shadowclone/core";
import { writeFrozenFile } from "./files";
import type { AcceptanceCheck } from "./schema";
import type { NativeDiagnostic } from "./diagnostics";

export function verificationFailure(options: {
  exitCode: number;
  stderr: string;
}): "fail" | "unknown" {
  return options.exitCode === 71 && /^sandbox-exec: /m.test(options.stderr) ? "unknown" : "fail";
}

export async function verifyNativeCandidate(options: {
  readonly directory: string;
  readonly homeDirectory: string;
  readonly scenario: { readonly acceptance: AcceptanceCheck | null };
  readonly blockedPaths?: readonly string[];
  readonly onDiagnostic?: (diagnostic: NativeDiagnostic) => Promise<void>;
}): Promise<{ correctness: "pass" | "fail" | "unknown"; evidence: string }> {
  if (!options.scenario.acceptance) {
    return { correctness: "unknown", evidence: "Advice completion is judged separately." };
  }

  if (process.platform !== "darwin") {
    return { correctness: "unknown", evidence: "The acceptance sandbox is unavailable." };
  }

  for (const file of options.scenario.acceptance.files) {
    await writeFrozenFile({ directory: options.directory, file });
  }

  const runtime = path.join(options.homeDirectory, "verification");
  await mkdir(runtime, { recursive: true, mode: 0o700 });
  const executables = await Promise.all(
    options.scenario.acceptance.commands.map(async ({ arguments: [executable] }) => {
      const located = executable ? Bun.which(executable) : null;

      return located ? path.dirname(await realpath(located)) : null;
    }),
  );
  const runtimeExemptions = executables
    .filter((entry) => entry !== null)
    .map((entry) => `(require-not (subpath ${JSON.stringify(entry)}))`)
    .join("");
  const profile = [
    "(version 1)(allow default)(deny network*)(deny file-write*)",
    `(allow file-write* (subpath ${JSON.stringify(options.directory)})(subpath ${JSON.stringify(runtime)})(literal "/dev/null"))`,
    ...[os.homedir(), ...(options.blockedPaths ?? [])].map(
      (entry) =>
        `(deny file-read* (require-all (subpath ${JSON.stringify(entry)})${runtimeExemptions}))`,
    ),
    `(allow file-read* (subpath ${JSON.stringify(options.directory)})(subpath ${JSON.stringify(runtime)}))`,
  ].join("");
  const evidence: string[] = [];

  for (const check of options.scenario.acceptance.commands) {
    const directory = await realpath(path.resolve(options.directory, check.directory));

    if (
      directory !== options.directory &&
      !directory.startsWith(`${options.directory}${path.sep}`)
    ) {
      return {
        correctness: "unknown",
        evidence: "Acceptance command directory escapes its workspace.",
      };
    }

    const [executable, ...arguments_] = check.arguments;
    const located = executable ? Bun.which(executable) : null;
    const resolved = located ? await realpath(located) : null;

    if (!resolved) {
      return { correctness: "unknown", evidence: "An acceptance executable is unavailable." };
    }

    const response = await runProcess({
      arguments: ["sandbox-exec", "-p", profile, resolved, ...arguments_],
      cwd: directory,
      environment: {
        PATH: process.env.PATH,
        HOME: runtime,
        TMPDIR: runtime,
        CI: "1",
        NX_DAEMON: "false",
        NX_SOCKET_DIR: runtime,
        XDG_CACHE_HOME: runtime,
      },
      timeoutMilliseconds: 120_000,
      maximumOutputBytes: 131072,
    });
    evidence.push(
      `${check.arguments.join(" ")}\nexit ${response.exitCode}\n${response.stdout}\n${response.stderr}`,
    );

    if (response.exitCode !== 0) {
      if (verificationFailure(response) === "unknown")
        await options.onDiagnostic?.({
          stage: "verification",
          confirmedInfrastructure: true,
          message: "Acceptance sandbox failed to start.",
          details: `${response.exitCode}\n${response.stderr}`,
        });
      return {
        correctness: verificationFailure(response),
        evidence: evidence.join("\n").slice(-16000),
      };
    }
  }

  return { correctness: "pass", evidence: evidence.join("\n").slice(-16000) };
}
