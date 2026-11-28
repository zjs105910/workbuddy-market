import { lstat, readdir } from "node:fs/promises";
import path from "node:path";
import type { ProjectPaths } from "@shadowclone/core";
import { materializeSnapshot } from "@shadowclone/redact";
import { parseSkillDocument, portableSkillNameSchema } from "@shadowclone/skills";

export type PersonalSkill = {
  readonly name: string;
  readonly description: string;
  readonly files: Readonly<Record<string, string>>;
};

const maximumSkillFiles = 32;
const maximumSkillFileBytes = 128_000;
const textExtensions = [
  ".md",
  ".txt",
  ".json",
  ".yaml",
  ".yml",
  ".toml",
  ".sh",
  ".py",
  ".ts",
  ".js",
] as const;

async function skillDirectory(options: {
  readonly paths: ProjectPaths;
  readonly name: string;
}): Promise<string | null> {
  const home = path.dirname(options.paths.shadowcloneDirectory);

  for (const root of [".agents/skills", ".claude/skills"]) {
    const directory = path.join(home, root, options.name);
    const metadata = await lstat(directory).catch(() => null);

    if (metadata?.isDirectory() && !metadata.isSymbolicLink()) {
      return directory;
    }
  }

  return null;
}

async function textFiles(options: {
  readonly directory: string;
  readonly relative: string;
  readonly depth: number;
}): Promise<readonly string[]> {
  const entries = await readdir(
    path.join(options.directory, options.relative),
    { withFileTypes: true },
  );
  const files: string[] = [];

  for (const entry of entries.sort((left, right) =>
    left.name.localeCompare(right.name),
  )) {
    const relative = path.join(options.relative, entry.name);

    if (
      entry.isDirectory() &&
      !entry.name.startsWith(".") &&
      options.depth < 3
    ) {
      files.push(
        ...(await textFiles({
          directory: options.directory,
          relative,
          depth: options.depth + 1,
        })),
      );
    } else if (
      entry.isFile() &&
      textExtensions.some((extension) => entry.name.endsWith(extension))
    ) {
      files.push(relative);
    }
  }

  return files;
}

export async function readPersonalSkill(options: {
  readonly paths: ProjectPaths;
  readonly name: string;
}): Promise<PersonalSkill> {
  const name = portableSkillNameSchema.parse(options.name);
  const directory = await skillDirectory({ paths: options.paths, name });

  if (directory === null) {
    throw new Error(
      `Personal skill ${name} was not found in ~/.agents/skills or ~/.claude/skills`,
    );
  }

  const relativePaths = await textFiles({ directory, relative: "", depth: 0 });

  if (!relativePaths.includes("SKILL.md")) {
    throw new Error(`Personal skill ${name} has no SKILL.md`);
  }

  if (relativePaths.length > maximumSkillFiles) {
    throw new Error(`Personal skill ${name} has too many files to copy`);
  }

  const files: Record<string, string> = {};

  for (const relativePath of relativePaths) {
    const snapshot = await materializeSnapshot({
      filePath: path.join(directory, relativePath),
      roots: [directory],
      maximumBytes: maximumSkillFileBytes,
      parse: (text) => text,
    });

    if (snapshot === null) {
      continue;
    }

    if (snapshot.parsed !== snapshot.redacted) {
      throw new Error(
        `Personal skill ${name} contains text that looks like a credential; review it before copying it into a repository`,
      );
    }

    files[relativePath.split(path.sep).join("/")] = snapshot.parsed;
  }

  const document = parseSkillDocument(files["SKILL.md"] ?? "");

  if (document.metadata.name !== name) {
    throw new Error(`Personal skill ${name} declares a different name`);
  }

  return { name, description: document.metadata.description, files };
}
