import { isRecord, readBoolean } from "../record";
import type { AgentEvent, FileTextRef } from "../types";
import { createClaudeBaseEvent } from "./claudeBase";

function blockText(value: unknown): string | null {
  if (!isRecord(value)) {
    return null;
  }

  if (typeof value.content === "string") {
    return value.content;
  }

  return typeof value.text === "string" ? value.text : null;
}

function contentContainsMarker(content: unknown, marker: string): boolean {
  if (typeof content === "string") {
    return content.includes(marker);
  }

  if (!Array.isArray(content)) {
    return false;
  }

  return content.some((value) => blockText(value)?.includes(marker) ?? false);
}

function classifyUserContent(options: {
  readonly interrupted: boolean;
  readonly denied: boolean;
  readonly questionAnswered: boolean;
  readonly planResolved: boolean;
  readonly plainPrompt: boolean;
}): AgentEvent["kind"] {
  if (options.interrupted) {
    return "interruption";
  }

  if (options.denied) {
    return "permission-denied";
  }

  if (options.questionAnswered) {
    return "question-answered";
  }

  if (options.planResolved) {
    return "plan-resolved";
  }

  return options.plainPrompt ? "user-prompt" : "tool-result";
}

export function parseClaudeUser(options: {
  readonly record: Readonly<Record<string, unknown>>;
  readonly message: Readonly<Record<string, unknown>>;
  readonly ref: FileTextRef;
}): readonly AgentEvent[] {
  if (readBoolean(options.record, "isMeta")) {
    return [];
  }

  const base = createClaudeBaseEvent(options);
  const content = options.message.content;
  const interrupted = contentContainsMarker(
    content,
    "[Request interrupted by user",
  );
  const denied = contentContainsMarker(
    content,
    "user doesn't want to proceed with this tool use",
  );
  const questionAnswered = contentContainsMarker(
    content,
    "User has answered your questions",
  );
  const planResolved = contentContainsMarker(
    content,
    "The user has approved your plan",
  );
  const plainPrompt = typeof content === "string";

  const kind = classifyUserContent({
    interrupted,
    denied,
    questionAnswered,
    planResolved,
    plainPrompt,
  });

  return [
    {
      ...base,
      kind,
      tool: null,
      isError: readBoolean(options.record, "is_error"),
      textRef: plainPrompt && !interrupted && !denied ? options.ref : null,
    },
  ];
}
