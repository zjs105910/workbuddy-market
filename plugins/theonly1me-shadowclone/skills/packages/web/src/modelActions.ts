import { z } from "zod";
import type { HostRunner } from "./voice/collect";
import { createVoiceCapture } from "./voice/capture";
import { createBuildNames } from "./buildNames";
import type { GenerationEngine } from "./generationEngine";
import { browserJson } from "./security";
import { createSkillDrafts } from "./skillDrafts";
import type { BuildContext } from "@shadowclone/environment";

const generateRequestSchema = z.strictObject({ previewId: z.uuid() });

export function createModelActions(
  context: BuildContext & { readonly engine?: GenerationEngine; readonly hostRunner?: HostRunner },
) {
  const names = createBuildNames(context);
  const drafts = createSkillDrafts(context);
  const voice = createVoiceCapture(context);
  const voiceActions = new Map<string, (options: { readonly body: unknown; readonly signal: AbortSignal }) => Promise<unknown>>([
    ["/api/voice/status", () => voice.status()],
    ["/api/voice/consent", ({ body }) => voice.consent(body)],
    ["/api/voice/capture", ({ signal }) => voice.capture(signal)],
    ["/api/voice/rewrite", ({ body, signal }) => voice.rewrite(body, signal)],
    ["/api/voice/save", ({ body }) => voice.save(body)],
  ]);

  return async (options: {
    readonly pathname: string;
    readonly body: unknown;
    readonly signal: AbortSignal;
  }): Promise<Response | null> => {
    const voiceAction = voiceActions.get(options.pathname);

    if (voiceAction) return browserJson({ body: await voiceAction(options) });

    if (options.pathname === "/api/build-name") {
      return browserJson({ body: await names({ input: options.body, signal: options.signal }) });
    }

    if (options.pathname === "/api/skill/preview") {
      return browserJson({ body: await drafts.preview(options.body) });
    }

    if (options.pathname === "/api/skill/generate") {
      const { previewId } = generateRequestSchema.parse(options.body);
      const skill = await drafts.generate({
        id: previewId,
        signal: options.signal,
      });

      return browserJson({ body: { skill } });
    }

    return null;
  };
}
