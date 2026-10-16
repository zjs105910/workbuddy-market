import { z } from "zod";
import type { ReferenceRecord } from "./types";

const keyPattern = /^[a-z0-9][a-z0-9._-]*$/;
const datePattern = /^\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z)?$/;

const metadataSchema = z.strictObject({
  schema: z.literal(1),
  key: z.string().regex(keyPattern),
  title: z.string().min(1).max(200),
  summary: z.string().min(1).max(1_000),
  tags: z.array(z.string().min(1).max(80)).max(32),
  scope: z.enum(["global", "org", "project"]),
  originDirectory: z.string().min(1).nullable(),
  repositoryName: z.string().min(1).nullable(),
  source: z.enum(["user", "claude-memory", "claude-project-memory"]),
  sourceLocator: z.string().min(1).max(1_024),
  updatedAt: z.string().regex(datePattern),
});

const metadataFields = [
  "schema",
  "key",
  "title",
  "summary",
  "tags",
  "scope",
  "originDirectory",
  "repositoryName",
  "source",
  "sourceLocator",
  "updatedAt",
] as const;

function safeLocator(value: string): boolean {
  return (
    !value.startsWith("/") &&
    !value.includes("\\") &&
    value
      .split("/")
      .every((part) => part.length > 0 && part !== "." && part !== "..")
  );
}

function metadata(record: ReferenceRecord): Readonly<Record<string, unknown>> {
  return {
    schema: record.schema,
    key: record.key,
    title: record.title,
    summary: record.summary,
    tags: [...record.tags],
    scope: record.scope,
    originDirectory: record.originDirectory,
    repositoryName: record.repositoryName,
    source: record.source,
    sourceLocator: record.sourceLocator,
    updatedAt: record.updatedAt,
  };
}

export function renderReference(record: ReferenceRecord): string {
  const lines = metadataFields.map(
    (field) => `${field}: ${JSON.stringify(metadata(record)[field])}`,
  );

  return `---\n${lines.join("\n")}\n---\n\n${record.body.trim()}\n`;
}

export function parseReference(text: string): ReferenceRecord | null {
  const match = text.match(/^---\n([\s\S]*?)\n---\n(?:\n)?([\s\S]*)$/);

  if (!match?.[1] || match[2] === undefined) {
    return null;
  }

  const values: Record<string, unknown> = {};
  const lines = match[1].split("\n");

  if (lines.length !== metadataFields.length) {
    return null;
  }

  for (const line of lines) {
    const separator = line.indexOf(": ");

    if (separator < 1) {
      return null;
    }

    const field = line.slice(0, separator);

    if (field in values) {
      return null;
    }

    try {
      values[field] = JSON.parse(line.slice(separator + 2));
    } catch {
      return null;
    }
  }

  const parsed = metadataSchema.safeParse(values);

  if (!parsed.success || !safeLocator(parsed.data.sourceLocator)) {
    return null;
  }

  const locationValid =
    parsed.data.scope === "global"
      ? parsed.data.originDirectory === null &&
        parsed.data.repositoryName === null
      : parsed.data.scope === "org"
        ? parsed.data.originDirectory !== null &&
          parsed.data.repositoryName === null
        : parsed.data.originDirectory !== null &&
          parsed.data.repositoryName !== null;

  if (!locationValid) {
    return null;
  }

  const body = match[2].trim();

  if (parsed.data.scope === "global") {
    return {
      ...parsed.data,
      scope: "global",
      originDirectory: null,
      repositoryName: null,
      body,
    };
  }

  if (parsed.data.scope === "org" && parsed.data.originDirectory !== null) {
    return {
      ...parsed.data,
      scope: "org",
      originDirectory: parsed.data.originDirectory,
      repositoryName: null,
      body,
    };
  }

  if (
    parsed.data.originDirectory === null ||
    parsed.data.repositoryName === null
  ) {
    return null;
  }

  return {
    ...parsed.data,
    scope: "project",
    originDirectory: parsed.data.originDirectory,
    repositoryName: parsed.data.repositoryName,
    body,
  };
}
