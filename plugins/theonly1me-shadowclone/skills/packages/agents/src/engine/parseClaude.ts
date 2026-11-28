import { claudeTrace } from "./claudeTrace";
import type { EngineRun, PermissionDenial } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
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

function assistantText(record: Readonly<Record<string, unknown>>): string {
  const message = record.message;

  if (!isRecord(message) || !Array.isArray(message.content)) {
    return "";
  }

  return message.content
    .flatMap((block) =>
      isRecord(block) &&
      readString(block, "type") === "text" &&
      readString(block, "text") !== null
        ? [readString(block, "text") ?? ""]
        : [],
    )
    .join("");
}

function permissionDenials(value: unknown): readonly PermissionDenial[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value.flatMap((entry) => {
    if (!isRecord(entry)) {
      return [];
    }

    const toolName =
      readString(entry, "tool_name") ?? readString(entry, "toolName");

    return toolName
      ? [
          {
            toolName,
            toolUseId:
              readString(entry, "tool_use_id") ??
              readString(entry, "toolUseId"),
          },
        ]
      : [];
  });
}

const commandUnavailableMarker = "isn't available in this environment";

function readErrors(
  record: Readonly<Record<string, unknown>>,
): readonly string[] {
  const value = record.errors;

  if (!Array.isArray(value)) {
    return [];
  }

  return value.filter((item): item is string => typeof item === "string");
}

export function parseClaudeStream(options: {
  readonly stream: string;
  readonly fallbackSessionId: string;
}): EngineRun {
  const textParts: string[] = [];
  const { actions, resolvedModel } = claudeTrace(options.stream);
  let result: Readonly<Record<string, unknown>> | null = null;

  for (const line of options.stream.split("\n")) {
    if (line.trim().length === 0) {
      continue;
    }

    try {
      const parsed: unknown = JSON.parse(line);

      if (!isRecord(parsed)) {
        continue;
      }

      if (readString(parsed, "type") === "assistant") {
        textParts.push(assistantText(parsed));
      }

      if (readString(parsed, "type") === "result") {
        result = parsed;
      }
    } catch {}
  }

  const resultText = result ? readString(result, "result") : null;
  const streamedText = textParts.join("");
  const turns = result ? (readNumber(result, "num_turns") ?? 0) : 0;

  const isCommandUnavailable =
    turns === 0 &&
    actions.length === 0 &&
    typeof resultText === "string" &&
    resultText.includes(commandUnavailableMarker);
  const isError =
    result?.is_error === true || result === null || isCommandUnavailable;

  const errors = result ? readErrors(result) : [];
  const errorDetails =
    errors.length > 0
      ? errors.join("; ")
      : result
        ? readString(result, "subtype")
        : null;
  const errorMessage = isCommandUnavailable
    ? resultText
    : result?.is_error === true
      ? (resultText ?? errorDetails ?? "Claude reported an error")
      : result === null
        ? "Claude returned no result"
        : null;

  return {
    engine: "claude-code",
    resolvedModel,
    sessionId:
      (result ? readString(result, "session_id") : null) ??
      options.fallbackSessionId,
    transcriptPath: null,
    text: streamedText.length > 0 ? streamedText : (resultText ?? ""),
    structured: result?.structured_output ?? null,
    costUsd: result ? readNumber(result, "total_cost_usd") : null,
    durationMs: result ? (readNumber(result, "duration_ms") ?? 0) : 0,
    turns,
    isError,
    permissionDenials: permissionDenials(result?.permission_denials),
    actions,
    errorMessage,
  };
}
