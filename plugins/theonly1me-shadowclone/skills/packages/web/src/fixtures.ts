import { buildFixture } from "@shadowclone/builds/testing";
import type { EngineRun, EngineRunOptions } from "@shadowclone/agents";
import { createBrowserHandler } from "./handler";

export const syntheticSkill = {
  name: "measure-first",
  description: "Use when changing processing performance.",
  body: "Record a baseline, change one factor, and compare repeated measurements.",
};

export const syntheticBrief = {
  name: "",
  description: "",
  body: "Measure processing performance before changing code.",
};

export function generationResult(structured: unknown): EngineRun {
  return {
    engine: "claude-code",
    sessionId: "synthetic-session",
    transcriptPath: null,
    text: "",
    structured,
    costUsd: 0.01,
    durationMs: 1,
    turns: 1,
    isError: false,
    permissionDenials: [],
    actions: [],
    errorMessage: null,
  };
}

export async function browserFixture() {
  const context = await buildFixture();
  const calls: EngineRunOptions[] = [];
  const origin = "http://127.0.0.1:43801";
  const token = crypto.randomUUID();
  const createHandler = () =>
    createBrowserHandler({
      ...context,
      origin: () => origin,
      token,
      engine: {
        engine: "claude-code",
        runner: async (run) => {
          calls.push(run);

          return generationResult(syntheticSkill);
        },
      },
    });

  return {
    context,
    calls,
    origin,
    token,
    createHandler,
    request: (options: { readonly path: string; readonly body?: unknown }) =>
      new Request(`${origin}${options.path}`, {
        method: options.body === undefined ? "GET" : "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Origin: origin,
          "Content-Type": "application/json",
        },
        body:
          options.body === undefined ? undefined : JSON.stringify(options.body),
      }),
  };
}
