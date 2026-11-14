import { expect, test } from "bun:test";
import { buildClaudeArguments } from "./claudeCode";

test("a tool-using run loads no host settings, hooks, or MCP servers and opens no domains", () => {
  const arguments_ = buildClaudeArguments({
    sessionId: "00000000-0000-4000-8000-000000000000",
    run: {
      prompt: "private prompt",
      cwd: "/worktree",
      execution: { purpose: "evaluation" },
      systemPromptFile: "/profile.md",
      allowedTools: ["Edit"],
      permissionMode: "dontAsk",
    },
  });

  const settingSourcesIndex = arguments_.indexOf("--setting-sources");

  expect(arguments_[settingSourcesIndex + 1]).toBe("");
  expect(arguments_).toContain("--strict-mcp-config");
  expect(arguments_).toContain('{"mcpServers":{}}');
  expect(arguments_).toContain("--safe-mode");

  const settingsIndex = arguments_.indexOf("--settings");
  const settings = arguments_[settingsIndex + 1] ?? "";

  expect(settings).toContain('"disableAllHooks":true');
  expect(settings).toContain('"failIfUnavailable":true');
  expect(settings).toContain('"allowUnsandboxedCommands":false');
  expect(settings).toContain('"allowedDomains":[]');
});

test("a review run reads only inside the checkout and loads none of its customizations", () => {
  const arguments_ = buildClaudeArguments({
    sessionId: "00000000-0000-4000-8000-000000000000",
    run: {
      prompt: "review",
      cwd: "/work/head",
      execution: { purpose: "review" },
      allowedTools: ["Read", "Grep", "Glob", "Agent"],
      permissionMode: "dontAsk",
    },
  });
  const toolsIndex = arguments_.indexOf("--tools");
  const settings = JSON.parse(arguments_[arguments_.indexOf("--settings") + 1] ?? "{}");

  expect(arguments_).toContain("--restricted");
  expect(arguments_).toContain("--safe-mode");
  expect(arguments_[toolsIndex + 1]).toBe("Read,Grep,Glob,Agent");
  expect(settings.permissions.deny).toContain("Bash");
});

test("a review run that asks for a command tool is refused", () => {
  expect(() =>
    buildClaudeArguments({
      sessionId: "00000000-0000-4000-8000-000000000000",
      run: {
        prompt: "review",
        cwd: "/work/head",
        execution: { purpose: "review" },
        allowedTools: ["Read", "Bash"],
        permissionMode: "dontAsk",
      },
    }),
  ).toThrow("Review runs allow only Read, Grep, Glob, Agent");
});

test("a review run with the network on can search and fetch, but not reach cloud metadata hosts", () => {
  const arguments_ = buildClaudeArguments({
    sessionId: "00000000-0000-4000-8000-000000000000",
    run: {
      prompt: "review",
      cwd: "/work/head",
      execution: { purpose: "review", network: true },
      allowedTools: ["Read", "Grep", "Glob", "Agent", "WebFetch", "WebSearch"],
      permissionMode: "dontAsk",
    },
  });
  const settings = JSON.parse(arguments_[arguments_.indexOf("--settings") + 1] ?? "{}");

  expect(arguments_[arguments_.indexOf("--tools") + 1]).toBe("Read,Grep,Glob,Agent,WebFetch,WebSearch");
  expect(settings.permissions.deny).toContain("WebFetch(domain:169.254.169.254)");
  expect(settings.permissions.deny).not.toContain("WebFetch");
});
