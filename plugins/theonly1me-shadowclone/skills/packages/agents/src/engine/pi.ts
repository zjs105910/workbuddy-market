import { chmod, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { z } from "zod";
import { runProcess } from "@shadowclone/core";
import { validateEngineExecution } from "./execution";
import { renderPiBridge } from "./piBridge";
import { buildEnginePrompt } from "./prompt";
import { runnerEnvironment } from "./environment";
import type { EngineRun, EngineRunOptions } from "./types";
import { requestPiSocket } from "./piSocket";

export const piModelSchema = z.strictObject({ id: z.string(), name: z.string() });
const resultSchema = z.union([
  z.strictObject({ text: z.string().max(1048576), model: z.string() }),
  z.strictObject({ models: z.array(piModelSchema) }),
  z.strictObject({ error: z.string() }),
]);

export async function requestPi(options: {
  readonly request: Readonly<Record<string, unknown>>;
  readonly model?: string;
  readonly signal?: AbortSignal;
  readonly environment?: Readonly<Record<string, string | undefined>>;
}): Promise<z.infer<typeof resultSchema>> {
  const environment = options.environment ?? process.env;
  if (Boolean(environment.SHADOWCLONE_PI_SOCKET) !== Boolean(environment.SHADOWCLONE_PI_TOKEN)) {
    throw new Error("Pi session bridge configuration is incomplete");
  }
  if (environment.SHADOWCLONE_PI_SOCKET && environment.SHADOWCLONE_PI_TOKEN) {
    const result = resultSchema.parse(await requestPiSocket({
      socketPath: environment.SHADOWCLONE_PI_SOCKET, token: environment.SHADOWCLONE_PI_TOKEN,
      request: options.request, signal: options.signal,
    }));
    if ("error" in result) throw new Error(result.error);
    return result;
  }
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-pi-"));
  const requestPath = path.join(directory, "request.json");
  const resultPath = path.join(directory, "result.json");
  const extensionPath = path.join(directory, "bridge.mjs");

  try {
    await chmod(directory, 0o700);
    const input = JSON.stringify(options.request);
    if (Buffer.byteLength(input) > 1048576) throw new Error("Pi request exceeds limit");
    await Bun.write(requestPath, input);
    await chmod(requestPath, 0o600);
    await Bun.write(extensionPath, renderPiBridge());
    const result = await runProcess({
      arguments: [
        "pi", "--offline", "--print", "--no-session", "--no-tools",
        "--no-context-files", "--no-skills", "--no-prompt-templates", "--no-themes",
        "--extension", extensionPath,
        ...(options.model ? ["--model", options.model] : []),
        "/shadowclone-request",
      ],
      cwd: directory,
      environment: {
        ...(options.environment ?? runnerEnvironment({ engine: "pi" })),
        SHADOWCLONE_INTERNAL_RUN: "1",
        SHADOWCLONE_PI_REQUEST: requestPath,
        SHADOWCLONE_PI_RESULT: resultPath,
      },
      signal: options.signal,
      maximumOutputBytes: 1048576,
    });
    const output = Bun.file(resultPath);
    if (result.exitCode !== 0 || !await output.exists() || output.size > 1048576) {
      throw new Error("Pi command failed; check the selected model in Pi");
    }
    const parsed = resultSchema.safeParse(await output.json());
    if (!parsed.success) throw new Error("Invalid Pi bridge response");
    if ("error" in parsed.data) throw new Error(parsed.data.error);
    return parsed.data;
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
}

export async function availablePiModels(options: {
  readonly environment?: Readonly<Record<string, string | undefined>>;
  readonly signal?: AbortSignal;
} = {}): Promise<readonly z.infer<typeof piModelSchema>[]> {
  const result = await requestPi({ ...options, signal: options.signal ?? AbortSignal.timeout(5_000), request: { operation: "models" } });
  if (!("models" in result)) throw new Error("Invalid Pi model inventory");
  return result.models;
}

export async function runPi(options: EngineRunOptions): Promise<EngineRun> {
  validateEngineExecution(options);
  if (options.execution.purpose !== "learning") {
    throw new Error("Pi dispatch and evaluation are unavailable: execution restrictions are unqualified");
  }
  if (options.sessionId || options.maxBudgetUsd !== undefined || options.disallowedTools?.length) {
    throw new Error("Pi cannot enforce the requested execution options");
  }
  const startedAt = Date.now();
  const result = await requestPi({
    request: {
      prompt: await buildEnginePrompt({ run: options, outputSchemaInPrompt: true }),
      model: options.model,
      reasoningEffort: options.reasoningEffort,
      jsonOnly: options.outputSchema !== undefined,
    },
    model: options.model,
    signal: options.signal,
  });
  if (!("text" in result)) throw new Error("Invalid Pi learning response");
  let structured: unknown = null;
  if (options.outputSchema !== undefined) {
    try { structured = JSON.parse(result.text); }
    catch { throw new Error("Pi returned invalid structured output"); }
  }
  return {
    engine: "pi", resolvedModel: result.model, sessionId: crypto.randomUUID(),
    transcriptPath: null, text: result.text, structured, costUsd: null,
    durationMs: Date.now() - startedAt, turns: 1, isError: false,
    permissionDenials: [], actions: [], errorMessage: null,
  };
}
