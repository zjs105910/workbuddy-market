import path from "node:path";
import { lstat } from "node:fs/promises";
import { z } from "zod";
import type { ProjectPaths } from "@shadowclone/core";
import { ownedWrite } from "@shadowclone/core";
import { cloneSchema } from "./types";

const installationSchema = z.strictObject({
  clone: cloneSchema,
  pullUrl: z.url().nullable(),
  guidanceFingerprint: z.string().regex(/^[a-f0-9]{64}$/),
  installedAt: z.iso.datetime(),
});

export async function saveInstallation(options: {
  readonly paths: ProjectPaths;
  readonly installation: z.infer<typeof installationSchema>;
}): Promise<void> {
  const installation = installationSchema.parse(options.installation);

  await ownedWrite({
    path: path.join(
      options.paths.shadowcloneDirectory,
      "cloud",
      "installations",
      `${installation.clone.repositoryId}.json`,
    ),
    content: JSON.stringify(installation),
  });
}

export async function cloneStatus(paths: ProjectPaths) {
  const directory = path.join(paths.shadowcloneDirectory, "cloud", "installations");
  const statuses: {
    repository: string;
    bot: string;
    pullUrl: string | null;
    installedAt: string;
    guidanceFingerprint: string;
  }[] = [];
  const stats = await lstat(directory).catch(() => null);

  if (!stats?.isDirectory() || stats.isSymbolicLink()) {
    return statuses;
  }

  for await (const file of new Bun.Glob("*.json").scan({
    cwd: directory,
    absolute: true,
  })) {
    const parsed = installationSchema.safeParse(await Bun.file(file).json());

    if (!parsed.success) {
      continue;
    }

    const { clone, ...metadata } = parsed.data;

    statuses.push({
      repository: clone.repository,
      bot: clone.botLogin,
      ...metadata,
    });
  }

  return statuses;
}

export async function readInstallation(options: {
  readonly paths: ProjectPaths;
  readonly repository: string;
}): Promise<z.infer<typeof installationSchema> | null> {
  const directory = path.join(options.paths.shadowcloneDirectory, "cloud", "installations");
  const stats = await lstat(directory).catch(() => null);

  if (!stats?.isDirectory() || stats.isSymbolicLink()) {
    return null;
  }

  for await (const file of new Bun.Glob("*.json").scan({ cwd: directory, absolute: true })) {
    const parsed = installationSchema.safeParse(await Bun.file(file).json());

    if (parsed.success && parsed.data.clone.repository.toLowerCase() === options.repository.toLowerCase()) {
      return parsed.data;
    }
  }

  return null;
}
