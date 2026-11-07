import { z } from "zod";

export const verificationRecipeSchema = z.strictObject({
  name: z.string().min(1).max(100),
  kind: z.enum(["test", "cli", "ui"]),
  prerequisites: z.array(z.string().min(1).max(4096)).max(8).default([]),
  setup: z.array(z.string().min(1).max(4096)).max(8).default([]),
  run: z.array(z.string().min(1).max(4096)).min(1).max(16),
  evidence: z.array(z.string().min(1).max(1024)).max(16).default([]),
  cleanup: z.array(z.string().min(1).max(4096)).max(8).default([]),
});

export type VerificationRecipe = z.infer<typeof verificationRecipeSchema>;
