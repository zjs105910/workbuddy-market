import { z } from "zod";
import { voiceDraftSchema } from "./profile";

export const voiceStatusSchema = z.strictObject({
  consent: z.boolean(),
  allowed: z.boolean(),
  voiceFile: z.strictObject({
    path: z.string(),
    state: z.enum(["missing", "file", "link"]),
    target: z.string().nullable(),
  }),
});

export const voiceResultSchema = z.strictObject({
  draft: voiceDraftSchema,
  destination: z.string(),
  sourceCount: z.number().int().optional(),
});

export const voiceSavedSchema = z.strictObject({ path: z.string() });

export type VoiceStatus = z.infer<typeof voiceStatusSchema>;
