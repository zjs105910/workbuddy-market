import type { ClaudeMemoryKind } from "./types";

const memoryTypes: readonly ClaudeMemoryKind[] = [
  "user",
  "feedback",
  "reference",
  "project",
];

export function kindFromFilename(filename: string): ClaudeMemoryKind | null {
  if (filename === "MEMORY.md") {
    return "index";
  }

  if (filename.startsWith("user_") && filename.endsWith(".md")) {
    return "user";
  }

  if (filename.startsWith("feedback_") && filename.endsWith(".md")) {
    return "feedback";
  }

  if (filename.startsWith("reference_") && filename.endsWith(".md")) {
    return "reference";
  }

  if (filename.startsWith("project_") && filename.endsWith(".md")) {
    return "project";
  }

  return null;
}

function unquote(value: string): string {
  const trimmed = value.trim();

  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    try {
      const parsed: unknown = JSON.parse(trimmed);

      if (typeof parsed === "string") {
        return parsed;
      }
    } catch {
      return trimmed.slice(1, -1);
    }
  }

  return trimmed;
}

function field(frontmatter: string, name: string): string {
  const prefix = `${name}:`;
  const line = frontmatter
    .split("\n")
    .find((entry) => entry.startsWith(prefix));

  return line === undefined ? "" : unquote(line.slice(prefix.length));
}

export function kindFromType(type: string): ClaudeMemoryKind | null {
  return memoryTypes.find((memoryType) => memoryType === type) ?? null;
}

export function contentParts(text: string): {
  readonly name: string;
  readonly description: string;
  readonly modified: string;
  readonly type: string;
  readonly body: string;
} {
  const match = text.match(/^---\n([\s\S]*?)\n---\n(?:\n)?([\s\S]*)$/);

  if (!match?.[1] || match[2] === undefined) {
    return {
      name: "",
      description: "",
      modified: "",
      type: "",
      body: text.trim(),
    };
  }

  return {
    name: field(match[1], "name"),
    description: field(match[1], "description"),
    modified: field(match[1], "  modified"),
    type: field(match[1], "type") || field(match[1], "  type"),
    body: match[2].trim(),
  };
}
