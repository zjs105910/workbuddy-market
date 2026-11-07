import { z } from "zod";

export const buildNameSchema = z.strictObject({
  title: z.string().min(1).max(48),
  profile: z.string().min(1).max(420),
  abilities: z
    .array(z.strictObject({ skill: z.string().min(1).max(120), text: z.string().min(1).max(200) }))
    .min(1)
    .max(3),
  tradeoff: z.string().min(1).max(240),
});

export const buildNameResultSchema = z.strictObject({
  name: buildNameSchema,
  destination: z.string(),
});

export type BuildName = z.infer<typeof buildNameSchema>;
export type BuildNameResult = z.infer<typeof buildNameResultSchema>;
