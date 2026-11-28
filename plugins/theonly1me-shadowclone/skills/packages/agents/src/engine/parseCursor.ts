import type { EngineRun } from "./types";

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readString(
  record: Readonly<Record<string, unknown>>,
  key: string,
): string | null {
  const value = record[key];

  return typeof value === "string" ? value : null;
}

function readNumber(
  record: Readonly<Record<string, unknown>>,
  key: string,
): number | null {
  const value = record[key];

  return typeof value === "number" ? value : null;
}

function parseStructured(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function parseCursorStream(options: {
  readonly stream: string;
  readonly fallbackSessionId: string;
}): EngineRun {
  let sessionId = options.fallbackSessionId;
  let result: Readonly<Record<string, unknown>> | null = null;
  let turns = 0;

  for (const line of options.stream.split("\n")) {
    if (line.trim().length === 0) {
      continue;
    }

    let event: unknown;

    try {
      event = JSON.parse(line);
    } catch {
      continue;
    }

    if (!isRecord(event)) {
      continue;
    }

    sessionId = readString(event, "session_id") ?? sessionId;

    if (readString(event, "type") === "assistant") {
      turns += 1;
    }

    if (readString(event, "type") === "result") {
      result = event;
    }
  }

  const text = result ? (readString(result, "result") ?? "") : "";

  return {
    engine: "cursor-agent",
    sessionId,
    transcriptPath: null,
    text,
    structured: parseStructured(text),
    costUsd: null,
    durationMs: result ? (readNumber(result, "duration_ms") ?? 0) : 0,
    turns,
    isError: result === null || result.is_error === true,
    permissionDenials: [],
    actions: [],
    errorMessage: null,
  };
}
