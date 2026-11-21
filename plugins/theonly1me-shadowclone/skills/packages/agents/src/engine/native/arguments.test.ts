import { expect, test } from "bun:test";
import { nativeClaudeArguments } from "./claudeArguments";
import { nativeCodexArguments } from "./codexArguments";
import type { NativeEngineOptions } from "./types";

const options: NativeEngineOptions = {
  engine: "claude-code", prompt: "Synthetic task", directory: "/private/tmp/study/run/workspace",
  homeDirectory: "/private/tmp/study/run/home", memoryEnabled: true, access: "write",
  blockedPaths: ["/private/tmp/study", "/private/source"], protectedPaths: ["/private/tmp/study/run/workspace/AGENTS.md"],
};

test("native Claude retains native discovery and memory while denying external tools", () => {
  const arguments_ = nativeClaudeArguments(options);
  expect(arguments_).not.toContain("--safe-mode");
  expect(arguments_).not.toContain("--bare");
  expect(arguments_).not.toContain("--restricted");
  expect(arguments_).toContain("--add-dir");
  expect(arguments_).toContain("claude-opus-5-5");
  const settings = arguments_[arguments_.indexOf("--settings") + 1];
  expect(settings).toContain('"autoMemoryEnabled":true');
  expect(settings).toContain('"allowedDomains":[]');
  expect(settings).toContain('"/private/tmp/study","/private/source"');
  expect(settings).toContain('"allowRead":["/private/tmp/study/run/workspace","/private/tmp/study/run/home"');
  expect(settings).toContain('Read(//private/tmp/study/run/home/.claude/.credentials.json)');
  expect(settings).toContain('Edit(//private/tmp/study/run/workspace/AGENTS.md)');
  expect(arguments_).not.toContain("--allowedTools");
  expect(settings).toContain(".credentials.json");
});

test("bare Claude disables memory independently of native repository guidance", () => {
  const arguments_ = nativeClaudeArguments({ ...options, memoryEnabled: false });
  expect(arguments_).not.toContain("--safe-mode");
  expect(arguments_[arguments_.indexOf("--settings") + 1]).toContain('"autoMemoryEnabled":false');
});

test("native Codex enables memory and records a private session", () => {
  const arguments_ = nativeCodexArguments({ ...options, engine: "codex" });
  expect(arguments_).toContain("features.memories=true");
  expect(arguments_).toContain("memories.use_memories=true");
  expect(arguments_).toContain("features.skip_host_skill_discovery=false");
  expect(arguments_).not.toContain("project_doc_max_bytes=0");
  expect(arguments_).not.toContain("--ephemeral");
  expect(arguments_).toContain("gpt-6-sol");
  expect(arguments_.join(" ")).toContain('auth.json"="deny"');
  expect(arguments_.join(" ")).toContain("network={enabled=false}");
});

test("read-only and tool-free runs cannot acquire workspace write permissions", () => {
  for (const access of ["read", "none"] as const) {
    const arguments_ = nativeCodexArguments({ ...options, engine: "codex", access });
    expect(arguments_.join(" ")).toContain('workspace"="read"');
    expect(arguments_.join(" ")).not.toContain('workspace"="write"');
  }
  expect(nativeCodexArguments({ ...options, engine: "codex", access: "none" })).toContain("shell_tool");
});

test("native resume keeps the same model, permissions, and session", () => {
  const sessionId = "11111111-2222-4333-8444-555555555555";
  const codex = nativeCodexArguments({ ...options, engine: "codex", resumeSessionId: sessionId });
  expect(codex.slice(0, 5)).toEqual(["codex", "exec", "resume", sessionId, "-"]);
  expect(codex).not.toContain("-C");
  expect(codex).toContain("gpt-6-sol");
  expect(codex.join(" ")).toContain("network={enabled=false}");

  const claude = nativeClaudeArguments({ ...options, resumeSessionId: sessionId });
  expect(claude).toContain("--resume");
  expect(claude).toContain(sessionId);
  expect(claude).not.toContain("--no-session-persistence");
  expect(nativeClaudeArguments({ ...options, persistSession: true })).not.toContain("--no-session-persistence");
});

test("Codex grants Git writes and stub tools only when requested", () => {
  const plain = nativeCodexArguments({ ...options, engine: "codex" }).join(" ");
  expect(plain).toContain('workspace/.git"="deny"');
  expect(plain).not.toContain("PATH=");

  const git = nativeCodexArguments({
    ...options, engine: "codex",
    writablePaths: ["/private/tmp/study/run/workspace/.git", "/private/tmp/study/run/origin.git"],
    toolDirectory: "/private/tmp/study/run/home/bin",
  }).join(" ");
  expect(git).toContain('workspace/.git"="write"');
  expect(git).toContain('origin.git"="write"');
  expect(git).toContain('home/bin"="read"');
  expect(git).toContain('PATH="/private/tmp/study/run/home/bin:');
  expect(git).toContain('"/private/tmp/study"="deny"');
});

test("Claude accepts a requested model and effort and grants Git paths and stub tools only when asked", () => {
  const plain = nativeClaudeArguments(options);
  expect(plain[plain.indexOf("--model") + 1]).toBe("claude-opus-5-5");
  expect(plain[plain.indexOf("--effort") + 1]).toBe("medium");
  const gitDirectory = "/private/tmp/study/run/workspace/.git";
  expect(plain.join(" ")).toContain(`Edit(/${gitDirectory})`);

  const custom = nativeClaudeArguments({
    ...options, model: "claude-sonnet-5-5", effort: "high",
    writablePaths: [gitDirectory, "/private/tmp/study/run/origin.git"], toolDirectory: "/private/tmp/study/run/home/bin",
  });
  expect(custom[custom.indexOf("--model") + 1]).toBe("claude-sonnet-5-5");
  expect(custom[custom.indexOf("--effort") + 1]).toBe("high");
  const settings = custom[custom.indexOf("--settings") + 1] ?? "";
  expect(settings).not.toContain(`Edit(/${gitDirectory})`);
  expect(settings).toContain('"allowWrite":["/private/tmp/study/run/workspace","/private/tmp/study/run/workspace/.git","/private/tmp/study/run/origin.git"');
  expect(settings).toContain(`"denyWrite"`);
  expect(JSON.parse(settings).sandbox.filesystem.denyWrite).not.toContain(gitDirectory);
  expect(JSON.parse(settings).sandbox.filesystem.allowRead).toContain("/private/tmp/study/run/origin.git");
});

test("Codex accepts a requested model and effort", () => {
  const arguments_ = nativeCodexArguments({ ...options, engine: "codex", model: "gpt-6-sol", effort: "high" });
  expect(arguments_).toContain('model_reasoning_effort="high"');
});
