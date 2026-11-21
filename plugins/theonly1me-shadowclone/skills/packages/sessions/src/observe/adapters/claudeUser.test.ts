import { expect, test } from "bun:test";
import type { FileTextRef } from "../types";
import { parseClaudeUser } from "./claudeUser";

const ref: FileTextRef = {
  type: "file",
  sourcePath: "/tmp/transcript.jsonl",
  byteOffset: 0,
  byteLength: 10,
};

function kindOf(content: unknown): string | undefined {
  const [event] = parseClaudeUser({
    record: {
      type: "user",
      sessionId: "session-1",
      uuid: "event-1",
      timestamp: "2026-09-05T08:00:00.000Z",
      cwd: "/repo",
    },
    message: { id: "message-1", role: "user", content },
    ref,
  });

  return event?.kind;
}

const markers = [
  ["[Request interrupted by user]", "interruption"],
  ["The user doesn't want to proceed with this tool use.", "permission-denied"],
  ["User has answered your questions", "question-answered"],
  ["The user has approved your plan", "plan-resolved"],
] as const;

test("classifies markers carried as a plain string", () => {
  for (const [marker, kind] of markers) {
    expect(kindOf(marker)).toBe(kind);
  }
});

test("classifies markers carried in a text block", () => {
  for (const [marker, kind] of markers) {
    expect(kindOf([{ type: "text", text: marker }])).toBe(kind);
  }
});

test("classifies markers carried in a tool result block", () => {
  for (const [marker, kind] of markers) {
    expect(kindOf([{ type: "tool_result", content: marker }])).toBe(kind);
  }
});

test("leaves an ordinary text block as a tool result", () => {
  expect(kindOf([{ type: "text", text: "run the tests please" }])).toBe(
    "tool-result",
  );
});
