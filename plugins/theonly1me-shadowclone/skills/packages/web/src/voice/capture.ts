import { z } from "zod";
import { readConfig, readEffectiveConfig, setSourceEnabled, writeConfig } from "@shadowclone/core";
import { generationEngine, type GenerationEngine } from "../generationEngine";
import { generationDestination, structuredCall } from "../structuredCall";
import { collectWriting, type HostRunner, type Writing } from "./collect";
import { voiceFileState, writeVoiceFile } from "./file";
import {
  assertInvented,
  voiceDocument,
  voiceDraftSchema,
  voiceProfilePrompt,
  voiceProfileSchema,
  voiceSamplesPrompt,
  voiceSamplesSchema,
} from "./profile";
import type { BuildContext } from "@shadowclone/environment";

export const voiceLimits = {
  capture: { maximumCalls: 1, timeoutMilliseconds: 120_000, maximumCostUsd: 0.25 },
  rewrite: { maximumCalls: 1, timeoutMilliseconds: 30_000, maximumCostUsd: 0.05 },
} as const;

const consentRequestSchema = z.strictObject({ enabled: z.boolean() });
const rewriteRequestSchema = z.strictObject({ profile: voiceProfileSchema });

export function createVoiceCapture(
  context: BuildContext & { readonly engine?: GenerationEngine; readonly hostRunner?: HostRunner },
) {
  let sources: readonly Writing[] = [];
  let running = false;

  const exclusive = async <Output>(work: () => Promise<Output>): Promise<Output> => {
    if (running) throw new Error("Wait for the current voice request to finish");

    running = true;

    try {
      return await work();
    } finally {
      running = false;
    }
  };

  const status = async () => {
    const { config, policy } = await readEffectiveConfig({
      configPath: context.paths.configFile,
      managedConfigPath: context.paths.managedConfigFile,
    });

    return {
      consent: config.sources["github-writing"],
      allowed: policy.enabled && policy.allowedSources.includes("github-writing"),
      voiceFile: await voiceFileState(context.paths),
    };
  };

  return {
    status,

    async consent(body: unknown) {
      const { enabled } = consentRequestSchema.parse(body);

      if (enabled && !(await status()).allowed) {
        throw new Error("Your managed policy does not allow reading GitHub writing");
      }

      await writeConfig({
        configPath: context.paths.configFile,
        config: setSourceEnabled({ config: await readConfig({ configPath: context.paths.configFile }), source: "github-writing", enabled }),
      });

      if (!enabled) sources = [];

      return status();
    },

    capture: (signal: AbortSignal) =>
      exclusive(async () => {
        const writing = await collectWriting({ ...context, run: context.hostRunner, signal });

        if (writing.length < 3) throw new Error("Shadowclone found too little writing of your own to describe a voice");

        const connection = await generationEngine(context);
        const draft = await structuredCall({
          connection,
          prompt: voiceProfilePrompt(writing),
          schema: voiceDraftSchema,
          limits: voiceLimits.capture,
          cwd: context.cwd,
          signal,
          task: "describe your voice",
        });

        assertInvented({ draft, sources: writing.map((entry) => entry.text) });
        sources = writing;

        return { draft, destination: generationDestination(connection), sourceCount: writing.length };
      }),

    rewrite: (body: unknown, signal: AbortSignal) =>
      exclusive(async () => {
        const { profile } = rewriteRequestSchema.parse(body);

        if (sources.length === 0) throw new Error("Capture your voice before you rewrite the samples");

        const connection = await generationEngine({ ...context, tier: "fast" });
        const samples = await structuredCall({
          connection,
          prompt: voiceSamplesPrompt(profile),
          schema: voiceSamplesSchema,
          limits: voiceLimits.rewrite,
          cwd: context.cwd,
          signal,
          task: "rewrite the samples",
        });

        assertInvented({ draft: { profile, samples }, sources: sources.map((entry) => entry.text) });

        return { draft: { profile, samples }, destination: generationDestination(connection) };
      }),

    async save(body: unknown) {
      const draft = voiceDraftSchema.parse(body);

      if (sources.length > 0) assertInvented({ draft: { samples: draft.samples }, sources: sources.map((entry) => entry.text) });

      return { path: await writeVoiceFile({ paths: context.paths, content: voiceDocument(draft) }) };
    },
  };
}
