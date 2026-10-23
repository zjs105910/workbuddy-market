import { mkdir } from "node:fs/promises";
import path from "node:path";
import { runProcess } from "@shadowclone/core";
import { evaluationCommand } from "./evaluationIsolation";
import { redactSecrets } from "@shadowclone/redact";
import { claudeIsolationArguments, missingClaudeSandboxTools } from "./claudeIsolation";
import { runnerEnvironment } from "./environment";
import { validateEngineExecution } from "./execution";
import { parseClaudeStream } from "./parseClaude";
import type { EngineRun, EngineRunOptions } from "./types";

function appendList(options: {
  readonly arguments_: string[];
  readonly flag: string;
  readonly values: readonly string[] | undefined;
}): void {
  if (options.values === undefined || options.values.length === 0) {
    return;
  }

  options.arguments_.push(options.flag);
  options.arguments_.push(...options.values);
}

export function buildClaudeArguments(options: {
  readonly run: EngineRunOptions;
  readonly sessionId: string;
}): readonly string[] {
  validateEngineExecution(options.run);

  const arguments_ = [
    "claude",
    "-p",
    "--output-format",
    "stream-json",
    "--verbose",
    "--session-id",
    options.sessionId,
    "--setting-sources",
    "",
  ];

  arguments_.push(...claudeIsolationArguments(options.run));

  if (options.run.systemPromptFile) {
    arguments_.push(
      "--append-system-prompt-file",
      options.run.systemPromptFile,
    );
  }

  if (options.run.systemPrompt) {
    arguments_.push("--system-prompt", options.run.systemPrompt);
  }

  if (options.run.model) {
    arguments_.push("--model", options.run.model);
  }

  if (options.run.reasoningEffort) {
    arguments_.push("--effort", options.run.reasoningEffort);
  }

  if (options.run.permissionMode) {
    arguments_.push("--permission-mode", options.run.permissionMode);
  }

  if (options.run.maxBudgetUsd !== undefined) {
    arguments_.push("--max-budget-usd", options.run.maxBudgetUsd.toString());
  }

  if (options.run.outputSchema !== undefined) {
    arguments_.push("--json-schema", JSON.stringify(options.run.outputSchema));
  }

  appendList({
    arguments_,
    flag: "--allowedTools",
    values: options.run.allowedTools,
  });

  appendList({
    arguments_,
    flag: "--disallowedTools",
    values: options.run.disallowedTools,
  });

  return arguments_;
}

export function redactedFailure(options: {
  readonly run: EngineRun;
  readonly stderr: string;
  readonly exitCode: number;
}): string {
  const stderrText = options.stderr.trim();

  if (stderrText.length > 0) {
    return stderrText.length <= 1_000
      ? redactSecrets({ text: stderrText })
      : `Claude failed with exit code ${options.exitCode}; its diagnostic output was too large to display. Run shadowclone doctor for setup checks.`;
  }

  if (options.run.errorMessage) {
    return options.run.errorMessage.length <= 1_000
      ? redactSecrets({ text: options.run.errorMessage })
      : `Claude failed with exit code ${options.exitCode}; its diagnostic output was too large to display. Run shadowclone doctor for setup checks.`;
  }

  const resultText = options.run.text.trim();

  return resultText.length > 0 && resultText.length <= 1_000
    ? redactSecrets({ text: resultText })
    : `Process exited with code ${options.exitCode}`;
}

export async function runClaudeCode(
  options: EngineRunOptions,
): Promise<EngineRun> {
  if (options.execution.purpose === "learning") {
    const missing = missingClaudeSandboxTools({
      platform: process.platform,
      which: (name) => Bun.which(name),
    });

    if (missing.length > 0) {
      throw new Error(`Claude sandbox needs ${missing.join(" and ")} on Linux. Install the missing command(s) and retry.`);
    }
  }

  const sessionId = options.sessionId ?? crypto.randomUUID();
  const temporaryDirectory =
    options.execution.purpose === "evaluation"
      ? path.join(options.cwd, ".eval-runtime")
      : options.cwd;

  if (options.execution.purpose === "evaluation") {
    await mkdir(temporaryDirectory, { recursive: true, mode: 0o700 });
  }

  const {
    exitCode,
    stdout: stream,
    stderr,
  } = await runProcess({
    arguments: evaluationCommand({
      arguments: buildClaudeArguments({ run: options, sessionId }),
      run: options,
    }),
    cwd: options.cwd,
    environment: {
      ...runnerEnvironment({ engine: "claude-code" }),
      ...(options.execution.purpose === "evaluation"
        ? {
            TMPDIR: temporaryDirectory,
            TMP: temporaryDirectory,
            TEMP: temporaryDirectory,
          }
        : {}),
    },
    input: options.prompt,
    signal: options.signal,
  });

  const run = parseClaudeStream({ stream, fallbackSessionId: sessionId });

  if (exitCode !== 0) {
    return {
      ...run,
      isError: true,
      errorMessage: redactedFailure({ run, stderr, exitCode }),
    };
  }

  if (run.errorMessage) {
    return { ...run, errorMessage: redactSecrets({ text: run.errorMessage }) };
  }

  return run;
}
