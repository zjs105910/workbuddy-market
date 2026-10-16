import {
  maximumDiagnosticBytes,
  maximumErrorBytes,
  maximumOutputBytes,
} from "./limits";

export class ProcessLimitError extends Error {
  constructor(reason: "output" | "cancelled") {
    super(
      reason === "output"
        ? "Process output limit exceeded"
        : "Process cancelled or timed out",
    );
    this.name = "ProcessLimitError";
  }
}

async function readOutput(options: {
  readonly stream: ReadableStream<Uint8Array>;
  readonly maximumBytes: number;
  readonly overflow: () => void;
}): Promise<string> {
  const reader = options.stream.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;

  try {
    while (true) {
      const result = await reader.read();

      if (result.done) {
        return Buffer.concat(chunks).toString("utf8");
      }

      totalBytes += result.value.byteLength;

      if (totalBytes > options.maximumBytes) {
        options.overflow();

        throw new ProcessLimitError("output");
      }

      chunks.push(result.value);
    }
  } finally {
    await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }
}

export async function runProcess(options: {
  readonly arguments: readonly string[];
  readonly cwd: string;
  readonly environment: Readonly<Record<string, string | undefined>>;
  readonly input?: string;
  readonly signal?: AbortSignal;
  readonly timeoutMilliseconds?: number;
  readonly maximumOutputBytes?: number;
}): Promise<{
  readonly exitCode: number;
  readonly stdout: string;
  readonly stderr: string;
}> {
  const deadline = AbortSignal.timeout(options.timeoutMilliseconds ?? 600_000);
  const signal = options.signal
    ? AbortSignal.any([deadline, options.signal])
    : deadline;

  if (signal.aborted) {
    throw new ProcessLimitError("cancelled");
  }

  const child = Bun.spawn({
    cmd: [...options.arguments],
    cwd: options.cwd,
    env: { ...options.environment },
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
    detached: process.platform !== "win32",
  });

  const terminate = () => {
    try {
      if (process.platform !== "win32") {
        process.kill(-child.pid, "SIGKILL");
      } else {
        child.kill("SIGKILL");
      }
    } catch {
      child.kill("SIGKILL");
    }
  };

  signal.addEventListener("abort", terminate, { once: true });

  if (signal.aborted) {
    terminate();
  }

  try {
    const results = await Promise.allSettled([
      readOutput({
        stream: child.stdout,
        maximumBytes: options.maximumOutputBytes ?? maximumOutputBytes,
        overflow: terminate,
      }),
      readOutput({
        stream: child.stderr,
        maximumBytes: maximumErrorBytes,
        overflow: terminate,
      }),
      child.exited,
      (async () => {
        try {
          child.stdin.write(options.input ?? "");
          await child.stdin.flush();
        } finally {
          child.stdin.end();
        }
      })(),
    ]);

    if (signal.aborted) {
      throw new ProcessLimitError("cancelled");
    }

    const [stdout, stderr, exitCode] = results;

    for (const result of results) {
      if (result.status === "rejected") {
        throw result.reason;
      }
    }

    if (
      stdout?.status !== "fulfilled" ||
      stderr?.status !== "fulfilled" ||
      exitCode?.status !== "fulfilled"
    ) {
      throw new Error("Process did not complete");
    }

    return {
      exitCode: exitCode.value,
      stdout: stdout.value,
      stderr: stderr.value.slice(-maximumDiagnosticBytes),
    };
  } finally {
    terminate();
    signal.removeEventListener("abort", terminate);
  }
}
