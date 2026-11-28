import { Database } from "bun:sqlite";
import { readBoundedFile, safeFilePath, maximumTextBytes, projectPaths } from "@shadowclone/core";
import { redactSecrets } from "@shadowclone/redact";
import { captureRoots } from "./roots";
import { parseTextRef, type TextRef } from "./types";

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function selectJson(options: {
  readonly value: unknown;
  readonly path: readonly (string | number)[];
}): unknown {
  let selected = options.value;

  for (const part of options.path) {
    if (typeof part === "number") {
      if (!Array.isArray(selected)) {
        return null;
      }

      selected = selected[part];

      continue;
    }

    if (!isRecord(selected)) {
      return null;
    }

    selected = selected[part];
  }

  return selected;
}

function unwrapText(options: {
  readonly text: string;
  readonly unwrap: "user-query" | null;
}): string {
  if (options.unwrap === null) {
    return options.text;
  }

  const match = options.text.match(
    /<user_query>\s*([\s\S]*?)\s*<\/user_query>/,
  );

  return match?.[1] ?? "";
}

async function resolveSqliteText(
  ref: Extract<TextRef, { readonly type: "sqlite-blob" }>,
): Promise<string> {
  if (!(await Bun.file(ref.sourcePath).exists())) {
    return "";
  }

  let database: Database | null = null;

  try {
    database = new Database(ref.sourcePath, { readonly: true, strict: true });

    const row = database
      .query<{ readonly data: Uint8Array }, [string, number]>(
        "SELECT data FROM blobs WHERE id = ? AND length(data) <= ?",
      )
      .get(ref.blobId, maximumTextBytes);

    if (row === null) {
      return "";
    }

    const value: unknown = JSON.parse(new TextDecoder().decode(row.data));
    const selected = selectJson({ value, path: ref.jsonPath });

    return typeof selected === "string"
      ? unwrapText({ text: selected, unwrap: ref.unwrap })
      : "";
  } catch {
    return "";
  } finally {
    database?.close();
  }
}

export async function resolveRedacted(options: {
  readonly ref: TextRef;
  readonly roots?: readonly string[];
}): Promise<string> {
  const ref = parseTextRef(options.ref);

  if (ref === null) {
    return "";
  }

  const roots = options.roots ?? captureRoots(projectPaths);

  if (ref.type === "sqlite-blob") {
    const sourcePath = await safeFilePath({ filePath: ref.sourcePath, roots });

    if (sourcePath === null) {
      return "";
    }

    return redactSecrets({
      text: await resolveSqliteText({ ...ref, sourcePath }),
    });
  }

  const text = await readBoundedFile({
    filePath: ref.sourcePath,
    roots,
    maximumBytes: maximumTextBytes,
    offset: ref.byteOffset,
    length: ref.byteLength,
    fileIdentity: ref.fileIdentity,
    contentHash: ref.contentHash,
  });

  return redactSecrets({ text: text ?? "" });
}
