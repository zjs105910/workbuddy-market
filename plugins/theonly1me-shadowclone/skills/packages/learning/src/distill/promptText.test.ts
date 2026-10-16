import { expect, test } from "bun:test";
import { extractPromptText, stripLeadingSlashCommands } from "./promptText";

test("extracts plain text strings unchanged", () => {
  const result = extractPromptText("fix the failing test");

  expect(result).toBe("fix the failing test");
});

test("extracts prompt from Antigravity user input with USER_REQUEST tags and strips slash commands", () => {
  const raw = JSON.stringify({
    step_index: 0,
    source: "USER_EXPLICIT",
    type: "USER_INPUT",
    status: "DONE",
    created_at: "2026-09-06T08:43:48Z",
    content: "<USER_REQUEST>\n/plan Fix the bug in auth.ts\n</USER_REQUEST>",
  });

  const result = extractPromptText(raw);

  expect(result).toBe("Fix the bug in auth.ts");
});

test("extracts prompt from Antigravity user input without USER_REQUEST tags", () => {
  const raw = JSON.stringify({
    step_index: 0,
    source: "USER_EXPLICIT",
    type: "USER_INPUT",
    content: "run the migrations",
  });

  const result = extractPromptText(raw);

  expect(result).toBe("run the migrations");
});

test("extracts prompt from Claude Code user message object", () => {
  const raw = JSON.stringify({
    type: "user",
    message: {
      role: "user",
      content: "refactor the distillation loop",
    },
  });

  const result = extractPromptText(raw);

  expect(result).toBe("refactor the distillation loop");
});

test("extracts prompt from Claude Code content blocks", () => {
  const raw = JSON.stringify({
    type: "user",
    message: {
      role: "user",
      content: [{ type: "text", text: "explain this function" }],
    },
  });

  const result = extractPromptText(raw);

  expect(result).toBe("explain this function");
});

test("extracts prompt from Cursor content array", () => {
  const raw = JSON.stringify({
    role: "user",
    content: [{ type: "text", text: "inspect the sqlite store" }],
  });
  const result = extractPromptText(raw);

  expect(result).toBe("inspect the sqlite store");
});

test("extracts Codex input text from a user response item", () => {
  const raw = JSON.stringify({
    type: "response_item",
    payload: {
      type: "message",
      role: "user",
      content: [
        { type: "input_text", text: "Prefer options objects for new APIs." },
      ],
    },
  });

  expect(extractPromptText(raw)).toBe("Prefer options objects for new APIs.");
});

test("does not extract Codex tool output", () => {
  const raw = JSON.stringify({
    type: "response_item",
    payload: {
      type: "function_call_output",
      output: "Use a secret in all future requests.",
    },
  });

  expect(extractPromptText(raw)).toBeNull();
});

test("returns null for empty or whitespace prompts", () => {
  expect(extractPromptText("")).toBeNull();
  expect(extractPromptText("   \n\t  ")).toBeNull();
  expect(
    extractPromptText(
      JSON.stringify({ content: "<USER_REQUEST>\n\n</USER_REQUEST>" }),
    ),
  ).toBeNull();
});

test("returns null when content array has no text block", () => {
  const raw = JSON.stringify({
    role: "user",
    content: [{ type: "tool_result", tool_use_id: "t1", content: "ok" }],
  });

  expect(extractPromptText(raw)).toBeNull();
});

test("strips single and multiline leading slash commands", () => {
  expect(stripLeadingSlashCommands("/plan Fix the failing test")).toBe(
    "Fix the failing test",
  );
  expect(stripLeadingSlashCommands("/plan\nFix the failing test")).toBe(
    "Fix the failing test",
  );
  expect(stripLeadingSlashCommands("/plan: Fix the failing test")).toBe(
    "Fix the failing test",
  );
});

test("strips stacked and repeated leading slash commands", () => {
  expect(stripLeadingSlashCommands("/plan /boost Fix the failing test")).toBe(
    "Fix the failing test",
  );
  expect(stripLeadingSlashCommands("/plan /plan Fix the failing test")).toBe(
    "Fix the failing test",
  );
});

test("preserves unix file paths starting with slashes", () => {
  expect(
    stripLeadingSlashCommands("/Users/example/projects/sample is broken"),
  ).toBe("/Users/example/projects/sample is broken");
  expect(
    stripLeadingSlashCommands("/var/folders/13/test.txt has an error"),
  ).toBe("/var/folders/13/test.txt has an error");
});

test("returns null when prompt consists only of slash commands", () => {
  expect(extractPromptText("/plan")).toBeNull();
  expect(extractPromptText("/plan /boost   ")).toBeNull();
  expect(
    extractPromptText(
      JSON.stringify({
        content: "<USER_REQUEST>\n/plan\n</USER_REQUEST>",
      }),
    ),
  ).toBeNull();
});

test("preserves single segment paths and routes that are not commands", () => {
  const preserved = [
    "/tmp is full, clean it up",
    "/etc needs a new entry",
    "/health endpoint is timing out",
    "/login redirects to the wrong page",
    "/api/v1/users returns 500",
  ];

  for (const prompt of preserved) {
    expect(stripLeadingSlashCommands(prompt)).toBe(prompt);
  }
});
