import { z } from "zod";

export const learningModelChoiceSchema = z.strictObject({
  engine: z.enum(["claude-code", "codex", "cursor-agent", "pi"]),
  model: z.string().min(1).optional(),
  name: z.string(),
});
export const learningModelCatalogSchema = z.strictObject({
  choices: z.array(learningModelChoiceSchema),
  selected: z.object({ engine: z.string().optional(), model: z.string().optional() }),
});
export type LearningModelChoice = z.infer<typeof learningModelChoiceSchema>;
