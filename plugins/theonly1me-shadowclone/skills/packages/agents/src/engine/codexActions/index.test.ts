import { expect, test } from "bun:test";
import { canonicalPath } from "@shadowclone/core";
import { buildCodexArguments, codexProcessArguments } from "../codex";
import { parseCodexStream } from "../parseCodex";

function parseStreamEvents(events: readonly unknown[]) {
  return parseCodexStream({
    stream: events.map((event) => JSON.stringify(event)).join("\n"),
    fallbackSessionId: "fallback",
    durationMs: 20,
  });
}

test("retains ordered completed actions once and distinguishes failed commands", () => {
  const commandItem = {
    type: "item.completed",
    item: {
      id: "command",
      type: "command_execution",
      command: "bun test",
      exit_code: 1,
    },
  };
  const editItem = {
    type: "item.completed",
    item: {
      id: "edit",
      type: "file_change",
      status: "completed",
      changes: [{ path: "src/result.ts", kind: "update" }],
    },
  };
  const run = parseStreamEvents([
    { type: "thread.started", thread_id: "thread" },
    commandItem,
    commandItem,
    editItem,
    { type: "turn.completed" },
  ]);

  expect(run.actions).toEqual([
    { tool: "Bash", path: null, command: "bun test", succeeded: false },
    { tool: "Edit", path: "src/result.ts", succeeded: true },
  ]);
  expect(run.isError).toBeFalse();
});

test("rejects truncated streams and surfaces failures", () => {
  expect(parseStreamEvents([{ type: "thread.started" }]).isError).toBeTrue();

  const run = parseStreamEvents([
    { type: "turn.failed", error: { message: "Usage limit reached" } },
  ]);

  expect(run.errorMessage).toBe("Usage limit reached");
  expect(run.isError).toBeTrue();
});

test("native observations retain only confined relative edit paths", () => {
  const run = parseCodexStream({
    stream: [
      { type: "thread.started", thread_id: "thread" },
      { type: "item.completed", item: { id: "inside", type: "file_change", status: "completed",
        changes: [{ path: "/private/tmp/workspace/pilot/retry.ts" }] } },
      { type: "item.completed", item: { id: "outside", type: "file_change", status: "completed",
        changes: [{ path: "/private/tmp/other/secret.ts" }] } },
      { type: "turn.completed" },
    ].map((event) => JSON.stringify(event)).join("\n"),
    fallbackSessionId: "fallback", durationMs: 20, workspaceDirectory: "/private/tmp/workspace",
  });
  expect(run.actions[0]?.path).toBe("pilot/retry.ts");
  expect(run.actions[1]?.path).toBe("[redacted:absolute-path]");
});

test("evaluation forwards the exact model and only enables writes for execution", () => {
  const runConfig = {
    prompt: "task",
    cwd: "/tmp/task",
    model: "gpt-5.6-sol",
    reasoningEffort: "xhigh" as const,
    execution: {
      purpose: "evaluation" as const,
      access: "write" as const,
      blockedPaths: ["/private/profile"],
    },
  };
  const executionArguments = buildCodexArguments({
    run: runConfig,
    temporaryDirectory: "/private/tmp/shadowclone-codex-test",
  });

  expect(executionArguments).toContain("gpt-5.6-sol");
  expect(executionArguments).toContain('model_reasoning_effort="xhigh"');
  expect(executionArguments).not.toContain("--sandbox");
  expect(executionArguments).toContain(
    'default_permissions="shadowclone-evaluation"',
  );

  const permissionValue = executionArguments.find((argument) =>
    argument.startsWith("permissions.shadowclone-evaluation="),
  );

  expect(permissionValue).toContain(
    `${JSON.stringify(canonicalPath(runConfig.cwd))}="write"`,
  );
  expect(permissionValue).not.toContain('":tmpdir"');
  expect(permissionValue).not.toContain('":slash_tmp"');
  expect(executionArguments.join(" ")).toContain('":root"="deny"');
  expect(executionArguments.join(" ")).toContain('"/private/profile"="deny"');
  expect(executionArguments.join(" ")).toContain(
    '"/private/tmp/shadowclone-codex-test"="write"',
  );
  expect(
    codexProcessArguments({
      arguments: executionArguments,
      run: runConfig,
      platform: "darwin",
    }),
  ).toEqual(executionArguments);
  expect(executionArguments).toContain("--ephemeral");

  const readConfig = {
    ...runConfig,
    execution: { ...runConfig.execution, access: "read" as const },
  };

  expect(
    buildCodexArguments({ run: { ...readConfig, allowedTools: [] } }),
  ).toContain("read-only");
  expect(() =>
    buildCodexArguments({ run: { ...runConfig, maxBudgetUsd: 1 } }),
  ).toThrow("dollar budget");
});
