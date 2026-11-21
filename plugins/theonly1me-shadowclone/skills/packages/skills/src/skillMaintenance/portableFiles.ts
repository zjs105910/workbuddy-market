import { existsSync } from "node:fs";
import { cp, lstat, mkdir, rename, rm } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import {
  readLocalText,
  replaceLocalText,
  canonicalPath,
  type ProjectPaths,
} from "@shadowclone/core";

export const portableSkillNameSchema = z
  .string()
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);

export const portableSkillSchema = z
  .strictObject({
    name: portableSkillNameSchema,
    sourceDirectory: z.string().min(1),
    replicaDirectories: z.array(z.string().min(1)),
    baselineFingerprint: z.string().min(1),
    installationFingerprint: z.string().min(1).optional(),
    managedBy: z.enum(["starter", "adopted"]).optional().default("adopted"),
  })
  .transform((skill) => ({
    ...skill,
    installationFingerprint:
      skill.installationFingerprint ?? skill.baselineFingerprint,
  }));

const portableStateSchema = z.strictObject({
  version: z.literal(1),
  skills: z.array(portableSkillSchema),
});

export type PortableSkill = z.infer<typeof portableSkillSchema>;

function statePath(paths: ProjectPaths): string {
  return path.join(paths.shadowcloneDirectory, "portable-skills.json");
}

export async function readPortableSkills(
  paths: ProjectPaths,
): Promise<readonly PortableSkill[]> {
  const text = await readLocalText(statePath(paths));

  if (text === null) {
    return [];
  }

  try {
    return portableStateSchema.parse(JSON.parse(text)).skills;
  } catch {
    throw new Error("Invalid portable skill state");
  }
}

export async function writePortableSkills(options: {
  readonly paths: ProjectPaths;
  readonly skills: readonly PortableSkill[];
}): Promise<void> {
  const filePath = statePath(options.paths);

  await replaceLocalText({
    filePath,
    previous: await readLocalText(filePath),
    next: `${JSON.stringify({ version: 1, skills: options.skills }, null, 2)}\n`,
  });
}

export async function skillTreeFingerprint(
  directory: string,
): Promise<string | null> {
  if (!existsSync(directory)) {
    return null;
  }

  const rootStats = await lstat(directory);

  if (!rootStats.isDirectory() || rootStats.isSymbolicLink()) {
    throw new Error("Portable skill root must be a real directory");
  }

  const entries: string[] = [];

  for await (const entry of new Bun.Glob("**/*").scan({
    cwd: directory,
    dot: true,
    onlyFiles: false,
    followSymlinks: false,
  })) {
    entries.push(entry);
  }

  const hasher = new Bun.CryptoHasher("sha256");

  for (const relativePath of entries.sort()) {
    const absolutePath = path.join(directory, relativePath);
    const stats = await lstat(absolutePath);

    if (stats.isSymbolicLink()) {
      throw new Error("Portable skills cannot contain symbolic links");
    }

    hasher.update(`${relativePath}\0${stats.isDirectory() ? "d" : "f"}\0`);

    if (stats.isFile()) {
      hasher.update(await Bun.file(absolutePath).arrayBuffer());
    }
  }

  return hasher.digest("hex");
}

export async function replaceSkillDirectory(options: {
  readonly source: string;
  readonly destination: string;
}): Promise<void> {
  if (canonicalPath(options.source) === canonicalPath(options.destination)) {
    return;
  }

  await mkdir(path.dirname(options.destination), { recursive: true });

  const nonce = crypto.randomUUID();
  const temporary = `${options.destination}.shadowclone-${nonce}.tmp`;
  const backup = `${options.destination}.shadowclone-${nonce}.backup`;

  await cp(options.source, temporary, { recursive: true, errorOnExist: true });

  const exists = (await skillTreeFingerprint(options.destination)) !== null;

  try {
    if (exists) {
      await rename(options.destination, backup);
    }

    await rename(temporary, options.destination);

    if (exists) {
      await rm(backup, { recursive: true, force: true });
    }
  } catch (error) {
    await rm(temporary, { recursive: true, force: true });

    if (exists && (await skillTreeFingerprint(backup)) !== null) {
      await rename(backup, options.destination);
    }

    throw error;
  }
}
