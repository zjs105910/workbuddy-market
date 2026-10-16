import { expect, test } from "bun:test";
import { parseClaudeStream } from "./parseClaude";

test("records the resolved model and joins successful and failed tool results", () => {
  const stream = [
    { type: "system", subtype: "init", model: "claude-sonnet-5" },
    {
      type: "assistant",
      message: {
        content: [
          {
            type: "tool_use",
            id: "read-skill",
            name: "Read",
            input: { file_path: "/snapshot/skills/clean-code/SKILL.md" },
          },
          {
            type: "tool_use",
            id: "missing",
            name: "Read",
            input: { file_path: "/snapshot/missing" },
          },
          {
            type: "tool_use",
            id: "unanswered",
            name: "Read",
            input: { file_path: "/snapshot/unanswered" },
          },
        ],
      },
    },
    {
      type: "user",
      message: {
        content: [
          {
            type: "tool_result",
            tool_use_id: "missing",
            is_error: true,
            content: "not found",
          },
          {
            type: "tool_result",
            tool_use_id: "read-skill",
            content: "private body",
          },
        ],
      },
    },
    {
      type: "result",
      is_error: false,
      num_turns: 1,
      modelUsage: { "claude-sonnet-5": { inputTokens: 12 } },
    },
  ]
    .map((value) => JSON.stringify(value))
    .join("\n");
  const run = parseClaudeStream({ stream, fallbackSessionId: "fixture" });

  expect(run.resolvedModel).toBe("claude-sonnet-5");
  expect(run.actions.map((action) => action.succeeded)).toEqual([
    true,
    false,
    null,
  ]);
  expect(JSON.stringify(run.actions)).not.toContain("private body");
});
