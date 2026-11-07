import path from "node:path";
import { z } from "zod";
import { readLocalText } from "@shadowclone/core";
import { verificationRecipeSchema } from "./recipes";
import { conventionSchema } from "./conventionSchema";

export const harnessManifestPath = ".shadowclone/harness.json";

const manifestSchema = z.strictObject({
  version: z.literal(1),
  gate: z
    .strictObject({
      command: z.string().min(1),
      source: z.string().min(1),
      ciRunsGate: z.boolean(),
    })
    .nullable(),
  personal: z.boolean(),
  conventions: z.array(conventionSchema),
  sourceExtensions: z.array(z.string().regex(/^\.[a-z]+$/)),
  skills: z.array(z.string().min(1)),
  ruleKeys: z.array(z.string().min(1)),
  artifacts: z.record(z.string(), z.string().regex(/^[a-f0-9]{64}$/)),
  verification: z.array(verificationRecipeSchema).max(32).optional(),
});

export type HarnessManifest = z.infer<typeof manifestSchema>;

export async function readHarnessManifest(
  root: string,
): Promise<HarnessManifest | null> {
  const text = await readLocalText(path.join(root, harnessManifestPath));

  if (text === null) {
    return null;
  }

  try {
    return manifestSchema.parse(JSON.parse(text));
  } catch {
    throw new Error(
      "The committed .shadowclone/harness.json is invalid; restore it from version control before refreshing the harness",
    );
  }
}

export function renderHarnessManifest(manifest: HarnessManifest): string {
  const text = JSON.stringify(manifestSchema.parse(manifest), null, 2);

  return `${text.replace(/[^\x20-\x7e\n]/g, (character) => `\\u${character.charCodeAt(0).toString(16).padStart(4, "0")}`)}\n`;
}
