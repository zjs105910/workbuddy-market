import path from "node:path";
import { lstat } from "node:fs/promises";
import { z } from "zod";
import { assertRegularDestination } from "@shadowclone/core";
import { markdownLinkTargets } from "./linkTargets";

const metadataSchema = z
  .object({
    name: z
      .string()
      .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
      .max(64),
    description: z.string().trim().min(1).max(1024),
  })
  .passthrough();

export function parseSkillDocument(text: string) {
  if (Buffer.byteLength(text) > 48_000) {
    throw new Error("Skill exceeds the supported size");
  }

  const match = text.match(/^(---\r?\n)([\s\S]*?)(\r?\n---(?:\r?\n|$))/);

  if (!match?.[0] || !match[2]) {
    throw new Error("Skill needs YAML frontmatter");
  }

  const keys = new Set<string>();

  for (const line of match[2].split("\n")) {
    const keyMatch = line.match(
      /^(?:"([^"]+)"|'([^']+)'|([a-zA-Z0-9_-]+))\s*:/,
    );
    const key = keyMatch?.[1] ?? keyMatch?.[2] ?? keyMatch?.[3];

    if (!key) {
      continue;
    }

    if (keys.has(key)) {
      throw new Error("Skill frontmatter contains duplicate fields");
    }

    keys.add(key);
  }

  let metadata: z.infer<typeof metadataSchema>;

  try {
    metadata = metadataSchema.parse(Bun.YAML.parse(match[2]));
  } catch {
    throw new Error("Skill needs valid name and description metadata");
  }

  const body = text.slice(match[0].length);

  if (!body.trim() || body.split("\n").length > 500) {
    throw new Error("Skill body is empty or too large");
  }

  let fence: string | null = null;

  for (const line of body.split("\n")) {
    const match = line.match(/^\s*(`{3,}|~{3,})(.*)$/);
    const marker = match?.[1];

    if (!marker) {
      continue;
    }

    if (fence === null) {
      fence = marker;
    } else if (
      marker[0] === fence[0] &&
      marker.length >= fence.length &&
      !match?.[2]?.trim()
    ) {
      fence = null;
    }
  }

  if (fence !== null) {
    throw new Error("Skill has an unclosed code fence");
  }

  return { metadata, body, frontmatter: match[0] };
}

export async function validateSkillReferences(options: {
  readonly filePath: string;
  readonly text: string;
  readonly mentionedFiles: "required" | "optional";
}): Promise<void> {
  const directory = path.dirname(options.filePath);
  const references = new Set<string>();
  const mentions = new Set<string>();

  for (const reference of markdownLinkTargets(options.text)) {
    if (
      !/^[a-z][a-z0-9+.-]*:/i.test(reference) &&
      !reference.startsWith("#")
    ) {
      references.add(reference);
    }
  }

  for (const match of options.text.matchAll(
    /`((?:scripts|references|assets|agents)\/[a-zA-Z0-9_./-]+)`/g,
  ))
    if (match[1]) {
      mentions.add(match[1]);
    }

  for (const reference of new Set([...references, ...mentions])) {
    const target = path.resolve(directory, reference);

    if (!target.startsWith(`${directory}${path.sep}`)) {
      throw new Error("Skill reference escapes its directory");
    }

    assertRegularDestination(target);

    try {
      if (!(await lstat(target)).isFile()) {
        throw new Error("Not a file");
      }
    } catch {
      if (references.has(reference) || options.mentionedFiles === "required") {
        throw new Error("Skill references an unavailable local file");
      }
    }
  }
}
