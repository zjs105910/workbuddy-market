import { maximumTranscriptRecordBytes } from "@shadowclone/core";
import path from "node:path";
import { isRecord, readRecord, readString } from "../record";

export type CodexContext = {
  readonly sessionId: string;
  readonly cwd: string;
  readonly gitBranch: string | null;
};

function fallbackContext(sourcePath: string): CodexContext {
  return {
    sessionId: path.basename(sourcePath, ".jsonl"),
    cwd: "",
    gitBranch: null,
  };
}

function parseContext(options: {
  readonly sourcePath: string;
  readonly value: unknown;
}): CodexContext | null {
  if (
    !isRecord(options.value) ||
    readString(options.value, "type") !== "session_meta"
  ) {
    return null;
  }

  const payload = readRecord(options.value, "payload");

  if (payload === null) {
    return null;
  }

  const git = readRecord(payload, "git");

  return {
    sessionId:
      readString(payload, "id") ??
      fallbackContext(options.sourcePath).sessionId,
    cwd: readString(payload, "cwd") ?? "",
    gitBranch: git ? readString(git, "branch") : null,
  };
}

async function readFirstLine(sourcePath: string): Promise<unknown> {
  const reader = Bun.file(sourcePath).stream().getReader();
  const chunks: Uint8Array[] = [];
  let byteLength = 0;

  while (true) {
    const next = await reader.read();

    if (next.done) {
      break;
    }

    const lineEnd = next.value.indexOf(10);
    const chunk = lineEnd < 0 ? next.value : next.value.slice(0, lineEnd);

    if (byteLength + chunk.byteLength > maximumTranscriptRecordBytes) {
      await reader.cancel();

      return null;
    }

    chunks.push(chunk);
    byteLength += chunk.byteLength;

    if (lineEnd >= 0) {
      await reader.cancel();

      break;
    }
  }

  const line = new Uint8Array(byteLength);
  let offset = 0;

  for (const chunk of chunks) {
    line.set(chunk, offset);
    offset += chunk.byteLength;
  }

  try {
    return JSON.parse(new TextDecoder().decode(line));
  } catch {
    throw new Error("Codex transcript has an invalid session header");
  }
}

export async function getCodexContext(options: {
  readonly sourcePath: string;
  readonly values: readonly { readonly value: unknown }[];
}): Promise<CodexContext> {
  for (const line of options.values) {
    const context = parseContext({
      sourcePath: options.sourcePath,
      value: line.value,
    });

    if (context !== null) {
      return context;
    }
  }

  const context = parseContext({
    sourcePath: options.sourcePath,
    value: await readFirstLine(options.sourcePath),
  });

  return context ?? fallbackContext(options.sourcePath);
}
