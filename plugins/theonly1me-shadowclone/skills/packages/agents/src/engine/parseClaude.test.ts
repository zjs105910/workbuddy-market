import { expect, test } from "bun:test";
import { redactedFailure } from "./claudeCode";
import { parseClaudeStream } from "./parseClaude";

test("parses a synthetic local command stream as an error", () => {
  const stream = [
    JSON.stringify({
      type: "system",
      subtype: "local_command",
      content:
        "<local-command-stdout>/plan isn't available in this environment.</local-command-stdout>",
    }),
    JSON.stringify({
      is_error: false,
      duration_api_ms: 0,
      num_turns: 0,
      total_cost_usd: 0,
      result: "/plan isn't available in this environment.",
      type: "result",
      duration_ms: 34,
      session_id: "test-session",
    }),
  ].join("\n");

  const run = parseClaudeStream({
    stream,
    fallbackSessionId: "fallback",
  });

  expect(run.isError).toBeTrue();
  expect(run.errorMessage).toBe("/plan isn't available in this environment.");
  expect(run.turns).toBe(0);
  expect(run.actions).toEqual([]);
});

test("parses an explicit Claude error result as an error", () => {
  const stream = JSON.stringify({
    type: "result",
    is_error: true,
    result: "API rate limit exceeded",
    num_turns: 0,
    session_id: "error-session",
  });

  const run = parseClaudeStream({
    stream,
    fallbackSessionId: "fallback",
  });

  expect(run.isError).toBeTrue();
  expect(run.errorMessage).toBe("API rate limit exceeded");
});

test("parses a stream with no result as an error", () => {
  const stream = JSON.stringify({
    type: "system",
    content: "starting process",
  });

  const run = parseClaudeStream({
    stream,
    fallbackSessionId: "fallback",
  });

  expect(run.isError).toBeTrue();
  expect(run.errorMessage).toBe("Claude returned no result");
});

test("parses budget exhausted errors array as errorMessage", () => {
  const stream = JSON.stringify({
    type: "result",
    is_error: true,
    subtype: "error_max_budget_usd",
    errors: ["Reached maximum budget ($0.20)"],
    terminal_reason: "budget_exhausted",
    num_turns: 1,
    session_id: "budget-session",
  });

  const run = parseClaudeStream({
    stream,
    fallbackSessionId: "fallback",
  });

  expect(run.isError).toBeTrue();
  expect(run.errorMessage).toBe("Reached maximum budget ($0.20)");
});

test("redacts secrets before they become a failure message", () => {
  const message = redactedFailure({
    run: {
      engine: "claude-code",
      sessionId: "session",
      text: "",
      structured: null,
      costUsd: null,
      durationMs: 0,
      turns: 0,
      isError: true,
      permissionDenials: [],
      actions: [],
      transcriptPath: null,
      errorMessage: null,
    },
    stderr: "auth failed for sk-abcdefghijklmnop at /Users/dev/work/acme",
    exitCode: 1,
  });

  expect(message).not.toContain("sk-abcdefghijklmnop");
  expect(message).not.toContain("/Users/dev/work/acme");
  expect(message).toContain("[redacted:");
});

test("redacts secrets carried in the parsed result text", () => {
  const message = redactedFailure({
    run: {
      engine: "claude-code",
      sessionId: "session",
      text: "",
      structured: null,
      costUsd: null,
      durationMs: 0,
      turns: 0,
      isError: true,
      permissionDenials: [],
      actions: [],
      transcriptPath: null,
      errorMessage: ("token " + ["ghp", "1234567890abcdefghijklmnopqrstuvwxyzAB"].join("_") + " rejected"),
    },
    stderr: "",
    exitCode: 1,
  });

  expect(message).not.toContain(["ghp", "1234567890abcdefghijklmnopqrstuvwxyzAB"].join("_"));
  expect(message).toContain("[redacted:github-token]");
});

test("records the invoked skill name for Skill tool requests", () => {
  const stream = [
    JSON.stringify({ type: "system", subtype: "init", model: "claude-synthetic" }),
    JSON.stringify({ type: "assistant", message: { content: [{ type: "tool_use", id: "tool-1", name: "Skill", input: { skill: "names" } }] } }),
    JSON.stringify({ type: "user", message: { content: [{ type: "tool_result", tool_use_id: "tool-1", is_error: false }] } }),
    JSON.stringify({ type: "result", subtype: "success", is_error: false, result: "done", num_turns: 1 }),
  ].join("\n");

  const run = parseClaudeStream({ stream, fallbackSessionId: "fallback" });
  expect(run.actions).toEqual([expect.objectContaining({ tool: "Skill", command: "names", succeeded: true })]);
});
