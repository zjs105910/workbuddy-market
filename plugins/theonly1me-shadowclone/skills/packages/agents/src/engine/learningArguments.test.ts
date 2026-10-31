import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { buildClaudeArguments } from "./claudeCode";
import { buildCodexArguments, codexProcessEnvironment } from "./codex";

function valueAfter(options: {
  readonly arguments_: readonly string[];
  readonly flag: string;
}): string | undefined {
  const flagIndex = options.arguments_.indexOf(options.flag);

  return options.arguments_[flagIndex + 1];
}

test("learning ignores permissive Claude project settings and removes tools", async () => {
  const workingDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-claude-learning-"),
  );
  const settingsDirectory = path.join(workingDirectory, ".claude");

  await mkdir(settingsDirectory, { recursive: true });
  await Bun.write(
    path.join(settingsDirectory, "settings.json"),
    JSON.stringify({
      hooks: {
        SessionStart: [
          { hooks: [{ type: "command", command: "echo widened" }] },
        ],
      },
      permissions: { allow: ["Bash(*)", "WebFetch(*)", "mcp__unsafe__*"] },
    }),
  );

  const arguments_ = buildClaudeArguments({
    sessionId: "00000000-0000-4000-8000-000000000000",
    run: {
      prompt: "redacted evidence",
      cwd: workingDirectory,
      execution: { purpose: "learning" },
      outputSchema: { type: "object" },
      permissionMode: "dontAsk",
      allowedTools: [],
    },
  });

  expect(valueAfter({ arguments_, flag: "--setting-sources" })).toBe("");
  expect(valueAfter({ arguments_, flag: "--tools" })).toBe("");
  expect(arguments_).toContain("--safe-mode");
  expect(arguments_).not.toContain("--restricted");
  expect(arguments_).toContain("--no-session-persistence");
  expect(arguments_).toContain("--strict-mcp-config");
  expect(arguments_).not.toContain("user,project");
});

test("learning removes Codex instructions, integrations, state, and shell", () => {
  const arguments_ = buildCodexArguments({
    run: {
      prompt: "redacted evidence",
      cwd: "/tmp",
      execution: { purpose: "learning" },
      outputSchema: { type: "object" },
      permissionMode: "dontAsk",
      allowedTools: [],
    },
  });

  expect(arguments_).toContain("read-only");
  expect(arguments_).toContain("--ephemeral");
  expect(arguments_).toContain("--ignore-user-config");
  expect(arguments_).toContain("--ignore-rules");
  expect(arguments_).toContain("mcp_servers={}");
  expect(arguments_).toContain("project_doc_max_bytes=0");
  expect(arguments_).toContain("shell_tool");
  expect(arguments_).not.toContain("--max-budget-usd");
});

test("isolated Codex execution hides unrelated home-directory skills", () => {
  expect(
    codexProcessEnvironment({
      environment: {
        PATH: "/bin",
        DATABASE_URL: "private-database",
        GITHUB_TOKEN: ["private", "token"].join("-"),
      },
      temporaryDirectory: "/private/tmp/shadowclone-codex",
      userHome: "/Users/example",
    }),
  ).toEqual({
    PATH: "/bin",
    HOME: "/private/tmp/shadowclone-codex",
    TMPDIR: "/private/tmp/shadowclone-codex",
    TMP: "/private/tmp/shadowclone-codex",
    TEMP: "/private/tmp/shadowclone-codex",
    CODEX_HOME: "/Users/example/.codex",
  });
});

test("learning rejects a tool request before arguments are built", () => {
  expect(() =>
    buildClaudeArguments({
      sessionId: "00000000-0000-4000-8000-000000000000",
      run: {
        prompt: "redacted evidence",
        cwd: "/tmp",
        execution: { purpose: "learning" },
        permissionMode: "dontAsk",
        allowedTools: ["Read"],
      },
    }),
  ).toThrow("Learning cannot enable provider tools");
});
