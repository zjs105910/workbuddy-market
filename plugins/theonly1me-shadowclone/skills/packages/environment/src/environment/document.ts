import { z } from "zod";
import { parseSkillDocument } from "@shadowclone/skills";

export function editableSkillDocument(options: {
  readonly text: string;
  readonly name: string;
  readonly description: string;
}) {
  const match = options.text.match(/^---\r?\n([\s\S]*?)\r?\n---(?:\r?\n|$)/);

  if (options.text.startsWith("---") && !match) {
    throw new Error("Existing skill frontmatter is incomplete");
  }

  const keys = new Set<string>();

  for (const line of (match?.[1] ?? "").split("\n")) {
    const key = line.match(/^(?:"([^"]+)"|'([^']+)'|([a-zA-Z0-9_-]+))\s*:/);
    const name = key?.[1] ?? key?.[2] ?? key?.[3];

    if (!name) {
      continue;
    }

    if (keys.has(name)) {
      throw new Error("Existing skill frontmatter contains duplicate fields");
    }

    keys.add(name);
  }

  const metadata = match?.[1]
    ? z.record(z.string(), z.unknown()).parse(Bun.YAML.parse(match[1]))
    : {};

  if (metadata.name !== undefined && metadata.name !== options.name) {
    throw new Error("Existing skill name does not match its directory");
  }

  if (
    typeof metadata.description === "string" &&
    metadata.name === options.name
  ) {
    return parseSkillDocument(options.text);
  }

  if (
    metadata.description !== undefined &&
    typeof metadata.description !== "string"
  ) {
    throw new Error("Existing description needs manual repair");
  }

  const frontmatter = `---\n${Bun.YAML.stringify({ ...metadata, name: options.name, description: metadata.description || options.description }).trimEnd()}\n---\n`;

  return parseSkillDocument(
    `${frontmatter}${match?.[0] ? options.text.slice(match[0].length) : options.text}`,
  );
}
