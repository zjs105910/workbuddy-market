import path from "node:path";
import { z } from "zod";
import { fingerprint, readLocalText, replaceLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { integrationSchema, type Integration } from "./types";
import { integrationFilePath } from "./targets";

const stateSchema = z.strictObject({
  version: z.literal(1),
  integrations: z.array(integrationSchema),
});

async function remainingSharedOwners(options: {
  readonly integration: Integration;
  readonly remaining: readonly Integration[];
}): Promise<readonly Integration[]> {
  const verified = new Map<string, string>();
  for (const file of options.integration.files) {
    if (file.kind !== "skill") continue;
    const filePath = integrationFilePath({ integration: options.integration, file });
    const current = await readLocalText(filePath);
    if (current !== null && fingerprint(current) === file.fingerprint) {
      verified.set(filePath, file.fingerprint);
    }
  }
  return options.remaining.map(integration => ({
    ...integration,
    files: integration.files.map(file => {
      if (file.kind !== "skill") return file;
      const digest = verified.get(integrationFilePath({ integration, file }));
      return digest ? { ...file, fingerprint: digest } : file;
    }),
  }));
}

export async function readIntegrations(
  paths: ProjectPaths,
): Promise<readonly Integration[]> {
  const text = await readLocalText(
    path.join(paths.shadowcloneDirectory, "integrations.json"),
  );

  if (text === null) {
    return [];
  }

  let value: unknown;

  try {
    value = JSON.parse(text);
  } catch {
    throw new Error(
      "Invalid native integration manifest; restore it before changing installations",
    );
  }

  const result = stateSchema.safeParse(value);

  if (!result.success) {
    throw new Error(
      "Invalid native integration manifest; restore it before changing installations",
    );
  }

  return result.data.integrations;
}

export async function saveIntegration(options: {
  readonly paths: ProjectPaths;
  readonly integration: Integration;
  readonly remove?: boolean;
}): Promise<void> {
  const filePath = path.join(
    options.paths.shadowcloneDirectory,
    "integrations.json",
  );
  const previous = await readLocalText(filePath);
  const integrations = await readIntegrations(options.paths);
  const kept = integrations.filter(
    (entry) => entry.id !== options.integration.id,
  );
  const updated = options.remove
    ? await remainingSharedOwners({ integration: options.integration, remaining: kept })
    : [...kept, options.integration];

  await replaceLocalText({
    filePath,
    previous,
    next: `${JSON.stringify({ version: 1, integrations: updated }, null, 2)}\n`,
  });
}
