import { z } from "zod";
import { runAutomaticLearning } from "@shadowclone/learning";

export const nativeModelSchema = z.object({
  engine: z.enum(["claude-code", "codex", "cursor-agent", "pi"]).optional(),
  model: z.string().min(1).max(512).optional(),
});

export async function automaticLearning(arguments_: readonly string[]): Promise<void> {
  const sessionKeys: string[] = [];
  const selection: Record<string, string> = {};
  for (let index = 0; index < arguments_.length; index += 2) {
    const flag = arguments_[index];
    const value = arguments_[index + 1];
    if (!value) throw new Error("Invalid internal learning request");
    if (flag === "--session-key") sessionKeys.push(value);
    else if (flag === "--engine") selection.engine = value;
    else if (flag === "--model") selection.model = value;
    else throw new Error("Invalid internal learning request");
  }
  await runAutomaticLearning({ sessionKeys, ...nativeModelSchema.parse(selection) });
}
