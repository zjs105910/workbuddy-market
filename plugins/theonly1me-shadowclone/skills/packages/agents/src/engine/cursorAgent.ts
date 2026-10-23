import { runProcess } from "@shadowclone/core";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { runnerEnvironment } from "./environment";
import { validateEngineExecution } from "./execution";
import { parseCursorStream } from "./parseCursor";
import { buildEnginePrompt } from "./prompt";
import type { EngineRun, EngineRunOptions, PermissionMode } from "./types";

function validateCursorOptions(options: EngineRunOptions): void {
  validateEngineExecution(options);

  if (options.sessionId !== undefined) {
    throw new Error("Cursor cannot set a caller-provided session id");
  }

  if (options.maxBudgetUsd !== undefined) {
    throw new Error("Cursor cannot enforce a per-run dollar budget");
  }

  if (options.disallowedTools && options.disallowedTools.length > 0) {
    throw new Error("Cursor cannot enforce a granular tool denylist");
  }

  if (options.allowedTools && options.allowedTools.length > 0) {
    throw new Error("Cursor cannot enforce a granular tool allowlist");
  }

  const supportedModes: readonly (PermissionMode | undefined)[] = [
    undefined,
    "dontAsk",
    "plan",
  ];

  if (!supportedModes.includes(options.permissionMode)) {
    throw new Error("Cursor cannot honor this permission mode");
  }
}

export function buildCursorArguments(
  options: EngineRunOptions,
): readonly string[] {
  validateCursorOptions(options);

  const arguments_ = [
    "cursor-agent",
    "--print",
    "--output-format",
    "stream-json",
    "--sandbox",
    "enabled",
    "--mode",
    options.permissionMode === "plan" ? "plan" : "ask",
    "--workspace",
    options.cwd,
  ];

  if (options.model) {
    arguments_.push("--model", options.model);
  }

  return arguments_;
}

async function runCursorProcess(options: {
  readonly run: EngineRunOptions;
  readonly workspace: string;
  readonly environment?: Readonly<Record<string, string | undefined>>;
}): Promise<EngineRun> {
  const prompt = await buildEnginePrompt({
    run: options.run,
    outputSchemaInPrompt: true,
  });
  const fallbackSessionId = crypto.randomUUID();
  const { exitCode, stdout: stream } = await runProcess({
    arguments: [
      ...buildCursorArguments({ ...options.run, cwd: options.workspace }),
      "--trust",
    ],
    cwd: options.workspace,
    environment:
      options.environment ?? runnerEnvironment({ engine: "cursor-agent" }),
    input: prompt,
    signal: options.run.signal,
  });
  const run = parseCursorStream({ stream, fallbackSessionId });

  return exitCode === 0 ? run : { ...run, isError: true };
}

export async function runCursorAgent(
  options: EngineRunOptions,
): Promise<EngineRun> {
  validateCursorOptions(options);

  const requiresIsolation =
    options.execution.purpose === "learning" ||
    options.allowedTools?.length === 0;

  if (!requiresIsolation) {
    return runCursorProcess({ run: options, workspace: options.cwd });
  }

  const directory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-cursor-"),
  );
  const workspace = path.join(directory, "workspace");
  const isolatedConfigDirectory = path.join(directory, "config");
  const configDirectory = path.join(workspace, ".cursor");

  const deniedPermissions = [
    "Shell(*)",
    "Read(*)",
    "Write(*)",
    "WebFetch(*)",
    "Mcp(*:*)",
  ];

  await Promise.all([
    mkdir(configDirectory, { recursive: true }),
    mkdir(isolatedConfigDirectory, { recursive: true }),
  ]);
  await Promise.all([
    Bun.write(
      path.join(configDirectory, "cli.json"),
      JSON.stringify({
        version: 1,
        permissions: { allow: [], deny: deniedPermissions },
      }),
    ),
    Bun.write(
      path.join(isolatedConfigDirectory, "cli-config.json"),
      JSON.stringify({
        version: 1,
        editor: { vimMode: false },
        permissions: { allow: [], deny: deniedPermissions },
      }),
    ),
  ]);

  try {
    return await runCursorProcess({
      run: options,
      workspace,
      environment: {
        ...runnerEnvironment({ engine: "cursor-agent" }),
        CURSOR_CONFIG_DIR: isolatedConfigDirectory,
      },
    });
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}
