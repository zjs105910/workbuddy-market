import { expect, test } from "bun:test";
import {
  buildClaudeArguments,
  buildCodexArguments,
  buildCursorArguments,
  detectEngine,
  parseClaudeStream,
  parseCodexStream,
  parseCursorStream,
} from "./index";

test("parses a recorded Claude stream without spawning a process", async () => {
  const stream = await Bun.file(
    new URL("fixtures/claude-stream.jsonl", import.meta.url),
  ).text();
  const run = parseClaudeStream({
    stream,
    fallbackSessionId: "fallback",
  });

  expect(run.sessionId).toBe("session-fixture");
  expect(run.text).toBe("Implemented the focused change.");
  expect(run.structured).toEqual({ rules: [] });
  expect(run.costUsd).toBe(0.012);
  expect(run.turns).toBe(2);
  expect(run.permissionDenials).toEqual([
    { toolName: "Bash", toolUseId: "tool-1" },
  ]);
  expect(run.isError).toBeFalse();
});

test("builds bounded Claude arguments without a prompt or bypass mode", () => {
  const arguments_ = buildClaudeArguments({
    sessionId: "00000000-0000-4000-8000-000000000000",
    run: {
      prompt: "private prompt",
      cwd: "/worktree",
      execution: { purpose: "evaluation" },
      systemPromptFile: "/profile.md",
      allowedTools: ["Edit"],
      permissionMode: "dontAsk",
      reasoningEffort: "xhigh",
      maxBudgetUsd: 1,
    },
  });

  expect(arguments_).toContain("--append-system-prompt-file");
  expect(arguments_).toContain("--allowedTools");
  expect(arguments_).toContain("Edit");
  expect(arguments_).toContain("--setting-sources");
  expect(arguments_[arguments_.indexOf("--setting-sources") + 1]).toBe("");
  expect(arguments_).toContain("dontAsk");
  expect(arguments_[arguments_.indexOf("--effort") + 1]).toBe("xhigh");
  expect(arguments_).toContain("--safe-mode");
  expect(arguments_).not.toContain("private prompt");
  expect(arguments_).not.toContain("bypassPermissions");
  expect(arguments_).not.toContain("--dangerously-skip-permissions");
});

test("omits allowedTools flag when empty list is supplied", () => {
  const arguments_ = buildClaudeArguments({
    sessionId: "00000000-0000-4000-8000-000000000000",
    run: {
      prompt: "private prompt",
      cwd: "/worktree",
      execution: { purpose: "evaluation" },
      allowedTools: [],
      permissionMode: "dontAsk",
    },
  });

  expect(arguments_).not.toContain("--allowedTools");
});

test("parses recorded Codex and Cursor streams without tool results", async () => {
  const codexStream = await Bun.file(
    new URL("fixtures/codex-stream.jsonl", import.meta.url),
  ).text();
  const cursorStream = await Bun.file(
    new URL("fixtures/cursor-stream.jsonl", import.meta.url),
  ).text();
  const codex = parseCodexStream({
    stream: codexStream,
    fallbackSessionId: "fallback",
    durationMs: 20,
  });
  const cursor = parseCursorStream({
    stream: cursorStream,
    fallbackSessionId: "fallback",
  });

  expect(codex.sessionId).toBe("codex-session-fixture");
  expect(codex.structured).toEqual({ rules: [] });
  expect(codex.turns).toBe(1);
  expect(cursor.sessionId).toBe("cursor-session-fixture");
  expect(cursor.text).toBe('{"rules":[]}');
  expect(cursor.text).not.toContain("private tool result");
  expect(cursor.structured).toEqual({ rules: [] });
});

test("builds bounded provider arguments without prompts or bypass flags", () => {
  const run = {
    prompt: "private prompt",
    cwd: "/worktree",
    execution: { purpose: "evaluation" as const },
    allowedTools: [],
    permissionMode: "dontAsk" as const,
  };
  const codex = buildCodexArguments({ run });
  const cursor = buildCursorArguments(run);

  expect(codex).toContain("read-only");
  expect(codex).toContain("shell_tool");
  expect(cursor).toContain("ask");
  expect([...codex, ...cursor]).not.toContain("private prompt");
  expect([...codex, ...cursor]).not.toContain("--yolo");
  expect([...codex, ...cursor]).not.toContain(
    "--dangerously-bypass-approvals-and-sandbox",
  );
});

test("fails when a provider cannot enforce a requested ceiling", () => {
  expect(() =>
    buildCodexArguments({
      run: {
        prompt: "task",
        cwd: "/repo",
        execution: { purpose: "evaluation" },
        maxBudgetUsd: 1,
      },
    }),
  ).toThrow("dollar budget");
  expect(() =>
    buildCursorArguments({
      prompt: "task",
      cwd: "/repo",
      execution: { purpose: "evaluation" },
      disallowedTools: ["Bash(git push:*)"],
    }),
  ).toThrow("granular tool denylist");
});

test("detects authenticated engines in selection order", async () => {
  const checked: string[] = [];
  const detection = await detectEngine({
    purpose: "distill",
    probe: ({ command }) => {
      checked.push(command.join(" "));

      return Promise.resolve(true);
    },
  });

  expect(checked).toEqual([
    "claude --version",
    "claude auth status",
    "codex --version",
    "codex login status",
    "cursor-agent --version",
    "cursor-agent status",
    "pi --version",
    "pi --list-models",
  ]);
  expect(detection.availability[0]?.authenticated).toBeTrue();
  expect(detection.selectedEngine).toBe("claude-code");
  expect(detection.runner).not.toBeNull();
});

test("falls back to Codex when Claude is unavailable", async () => {
  const detection = await detectEngine({
    purpose: "distill",
    probe: ({ command }) =>
      Promise.resolve(command[0] === "codex" || command[0] === "cursor-agent"),
  });

  expect(detection.selectedEngine).toBe("codex");
});

test("selects only engines that support the requested purpose", async () => {
  const detection = await detectEngine({
    purpose: "eval",
    probe: () => Promise.resolve(true),
    allowedEngines: ["cursor-agent"],
  });

  expect(detection.selectedEngine).toBeNull();
  expect(detection.runner).toBeNull();
});
