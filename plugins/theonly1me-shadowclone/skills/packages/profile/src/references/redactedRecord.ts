import { resolveRedacted } from "@shadowclone/sessions";
import { parseReference, renderReference } from "./format";
import type { ReferenceRecord } from "./types";

async function resolveSlice(options: {
  readonly filePath: string;
  readonly root: string;
  readonly raw: string;
  readonly start: number;
  readonly end: number;
}): Promise<string> {
  const byteOffset = Buffer.byteLength(
    options.raw.slice(0, options.start),
    "utf8",
  );
  const value = options.raw.slice(options.start, options.end);
  const byteLength = Buffer.byteLength(value, "utf8");

  if (byteLength === 0) {
    return "";
  }

  return resolveRedacted({
    ref: {
      type: "file",
      sourcePath: options.filePath,
      byteOffset,
      byteLength,
      contentHash: new Bun.CryptoHasher("sha256").update(value).digest("hex"),
    },
    roots: [options.root],
  });
}

async function redactedField(options: {
  readonly field: string;
  readonly filePath: string;
  readonly root: string;
  readonly raw: string;
}): Promise<unknown> {
  const prefix = `${options.field}: `;
  const start = options.raw.indexOf(prefix);

  if (start < 0) {
    return null;
  }

  const valueStart = start + prefix.length;
  const newline = options.raw.indexOf("\n", valueStart);
  const valueEnd = newline < 0 ? options.raw.length : newline;
  const text = await resolveSlice({
    ...options,
    start: valueStart,
    end: valueEnd,
  });

  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export async function redactReference(options: {
  readonly record: ReferenceRecord;
  readonly filePath: string;
  readonly root: string;
  readonly raw: string;
}): Promise<ReferenceRecord | null> {
  const fields = await Promise.all(
    [
      "key",
      "title",
      "summary",
      "tags",
      "originDirectory",
      "repositoryName",
      "sourceLocator",
      "updatedAt",
    ].map((field) => redactedField({ ...options, field })),
  );

  const [
    key,
    title,
    summary,
    tags,
    originDirectory,
    repositoryName,
    sourceLocator,
    updatedAt,
  ] = fields;

  const header = options.raw.match(/^---\n[\s\S]*?\n---\n(?:\n)?/);

  if (
    header === null ||
    typeof key !== "string" ||
    typeof title !== "string" ||
    typeof summary !== "string" ||
    !Array.isArray(tags) ||
    !tags.every((tag) => typeof tag === "string") ||
    (originDirectory !== null && typeof originDirectory !== "string") ||
    (repositoryName !== null && typeof repositoryName !== "string") ||
    typeof sourceLocator !== "string" ||
    typeof updatedAt !== "string"
  ) {
    return null;
  }

  const body = (
    await resolveSlice({
      ...options,
      start: header[0].length,
      end: options.raw.length,
    })
  ).trim();

  const common = {
    schema: 1 as const,
    key,
    title,
    summary,
    tags,
    source: options.record.source,
    sourceLocator,
    updatedAt,
    body,
  };

  if (options.record.scope === "global") {
    if (originDirectory !== null || repositoryName !== null) {
      return null;
    }

    return parseReference(
      renderReference({
        ...common,
        scope: "global",
        originDirectory: null,
        repositoryName: null,
      }),
    );
  }

  if (options.record.scope === "org") {
    if (originDirectory === null || repositoryName !== null) {
      return null;
    }

    return parseReference(
      renderReference({
        ...common,
        scope: "org",
        originDirectory,
        repositoryName: null,
      }),
    );
  }

  if (originDirectory === null || repositoryName === null) {
    return null;
  }

  return parseReference(
    renderReference({
      ...common,
      scope: "project",
      originDirectory,
      repositoryName,
    }),
  );
}
