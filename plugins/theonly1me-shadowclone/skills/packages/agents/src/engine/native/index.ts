import path from "node:path";
import { mkdir, realpath } from "node:fs/promises";
import { runProcess } from "@shadowclone/core";
import { redactSecrets } from "@shadowclone/redact";
import { parseClaudeStream } from "../parseClaude";
import { parseCodexStream } from "../parseCodex";
import { nativeAuthentication } from "./auth";
import { nativeClaudeArguments } from "./claudeArguments";
import { nativeCodexArguments } from "./codexArguments";
import { nativeMetadata } from "./metadata";
import { nativeModels, type NativeEngineOptions, type NativeEngineRun } from "./types";

export { nativeModels } from "./types";
export type { NativeEngine, NativeEngineOptions, NativeEngineRun, NativeEngineRunner } from "./types";

export async function runNativeEngine(options: NativeEngineOptions): Promise<NativeEngineRun> {
  if (process.platform !== "darwin") {
    throw new Error("Native skills evaluation currently requires the macOS sandbox");
  }

  if (options.learningModel && (options.engine !== "codex" || options.access !== "none" || options.memoryEnabled)) {
    throw new Error("The learning model requires a tool-free Codex learning environment");
  }

  const directory = await realpath(options.directory);
  const home = await realpath(options.homeDirectory);

  if (directory === home || directory.startsWith(`${home}${path.sep}`) || home.startsWith(`${directory}${path.sep}`)) {
    throw new Error("Native evaluation requires separate workspace and home directories");
  }

  await mkdir(path.join(home, "tmp"), { recursive: true, mode: 0o700 });
  await mkdir(path.join(home, ".claude"), { recursive: true, mode: 0o700 });
  await mkdir(path.join(home, ".codex"), { recursive: true, mode: 0o700 });
  const authentication = await nativeAuthentication(options);

  try {
    const arguments_ = options.engine === "claude-code"
      ? nativeClaudeArguments(options)
      : nativeCodexArguments(options);

    if (options.engine === "codex" && options.outputSchema) {
      const schemaPath = path.join(home, "response-schema.json");

      await Bun.write(schemaPath, JSON.stringify(options.outputSchema), { mode: 0o600 });
      arguments_.push("--output-schema", schemaPath);
    }

    const environment = {
      ...authentication.environment,
      ...(options.toolDirectory
        ? { PATH: [options.toolDirectory, authentication.environment.PATH ?? process.env.PATH ?? ""].filter(Boolean).join(path.delimiter) }
        : {}),
      HOME: home,
      CODEX_HOME: path.join(home, ".codex"),
      CLAUDE_CONFIG_DIR: path.join(home, ".claude"),
      CLAUDE_CODE_PROJECT_DIR_NAME: "evaluation",
      CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: "1",
      CLAUDE_CODE_TMPDIR: path.join(home, "tmp"),
      DISABLE_AUTOUPDATER: "1",
      TMPDIR: path.join(home, "tmp"),
      TMP: path.join(home, "tmp"),
      TEMP: path.join(home, "tmp"),
    };
    const version = await runProcess({
      arguments: [options.engine === "codex" ? "codex" : "claude", "--version"],
      cwd: directory,
      environment,
      signal: options.signal,
    });
    const startedAt = Date.now();

    if (version.exitCode !== 0 || (options.expectedCliVersion && version.stdout.trim() !== options.expectedCliVersion)) {
      throw new Error("Native CLI version changed; repeat delivery qualification before evaluation");
    }

    const response = await runProcess({
      arguments: arguments_,
      cwd: directory,
      environment,
      input: options.prompt,
      signal: options.signal,
      maximumOutputBytes: 16_000_000,
    });
    const fallbackSessionId = crypto.randomUUID();
    await options.debugTransport?.({ stdout: response.stdout, stderr: response.stderr });
    const parsed = options.engine === "claude-code"
      ? parseClaudeStream({ stream: response.stdout, fallbackSessionId })
      : parseCodexStream({ stream: response.stdout, fallbackSessionId, durationMs: Date.now() - startedAt,
        workspaceDirectory: directory });
    const metadata = await nativeMetadata({
      stream: response.stdout,
      homeDirectory: home,
      sessionId: parsed.sessionId,
    });
    const resolvedModel = parsed.resolvedModel ?? metadata.resolvedModel;
    const requestedModel = options.model ?? options.learningModel ?? nativeModels[options.engine];
    const modelMatches = resolvedModel === requestedModel;

    return {
      ...parsed,
      resumableSessionId: parsed.sessionId === fallbackSessionId ? null : parsed.sessionId,
      resolvedModel,
      cliVersion: version.stdout.trim(),
      usage: metadata.usage,
      isError: parsed.isError || response.exitCode !== 0 || !modelMatches,
      errorMessage: response.exitCode !== 0
        ? redactSecrets({ text: response.stderr.trim() || parsed.errorMessage || "Native process failed" })
        : parsed.errorMessage ?? (!modelMatches
          ? `Requested ${requestedModel}; observed ${resolvedModel ?? "unknown model"}` : null),
    };
  } finally {
    await authentication.cleanup();
  }
}
