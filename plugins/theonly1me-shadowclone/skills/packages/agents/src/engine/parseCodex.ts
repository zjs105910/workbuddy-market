import { redactSecrets } from "@shadowclone/redact";
import { codexActions } from "./codexActions";
import type { EngineAction, EngineRun } from "./types";

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

function parseStructured(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function parseCodexStream(options: {
  readonly stream: string;
  readonly fallbackSessionId: string;
  readonly durationMs: number;
  readonly workspaceDirectory?: string;
}): EngineRun {
  let sessionId = options.fallbackSessionId;
  let text = "";
  let turns = 0;
  let isError = false;
  let errorMessage: string | null = null;

  const actions: EngineAction[] = [];
  const completedItems = new Set<string>();

  for (const line of options.stream.split("\n")) {
    if (line.trim().length === 0) {
      continue;
    }

    let event: unknown;

    try {
      event = JSON.parse(line);
    } catch {
      isError = true;
      continue;
    }

    if (!isRecord(event)) {
      continue;
    }

    const type = readString(event, "type");

    if (type === "thread.started") {
      sessionId = readString(event, "thread_id") ?? sessionId;
    }

    if (type === "turn.completed") {
      turns += 1;
    }

    if (type === "turn.failed" || type === "error") {
      isError = true;

      const error = isRecord(event.error) ? event.error : event;

      errorMessage = redactSecrets({
        text: readString(error, "message") ?? "Codex reported an error",
      });
    }

    const item = isRecord(event.item) ? event.item : null;

    if (type === "item.completed" && item !== null) {
      const id = readString(item, "id");

      if (id === null || !completedItems.has(id)) {
        actions.push(...codexActions(item, { workspaceDirectory: options.workspaceDirectory }));

        if (id !== null) {
          completedItems.add(id);
        }
      }
    }

    const itemType = item
      ? (readString(item, "item_type") ?? readString(item, "type"))
      : null;

    if (
      type === "item.completed" &&
      item !== null &&
      (itemType === "assistant_message" || itemType === "agent_message")
    ) {
      text = readString(item, "text") ?? text;
    }
  }

  const resolvedErrorMessage =
    errorMessage ?? (turns === 0 ? "Codex returned no completed turn" : null);

  return {
    engine: "codex",
    sessionId,
    transcriptPath: null,
    text,
    structured: parseStructured(text),
    costUsd: null,
    durationMs: options.durationMs,
    turns,
    isError: isError || turns === 0,
    permissionDenials: [],
    actions,
    errorMessage: resolvedErrorMessage,
  };
}
