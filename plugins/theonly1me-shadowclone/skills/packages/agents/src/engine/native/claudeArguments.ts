import path from "node:path";
import os from "node:os";
import { realpathSync } from "node:fs";
import { nativeModels, type NativeEngineOptions } from "./types";

export function nativeClaudeArguments(options: NativeEngineOptions): string[] {
  const memoryDirectory = path.join(options.homeDirectory, ".claude", "memory");
  const authenticationFile = path.join(options.homeDirectory, ".claude", ".credentials.json");
  const runtimeDirectories = ["claude", "node", "bun"].flatMap((name) => {
    const executable = Bun.which(name);

    return executable ? [path.dirname(executable), path.dirname(realpathSync(executable))] : [];
  });
  const extraWritable = options.writablePaths ?? [];
  const protectedPaths = [
    ...options.protectedPaths, authenticationFile, path.join(options.directory, ".git"),
    ...[".agents", ".codex", ".claude/skills", ".claude/CLAUDE.md", ".claude/settings.json",
      ".claude/settings.local.json", ".claude/plugins", ".claude/rules", ".claude.json", "CLAUDE.md"]
      .map((entry) => path.join(options.homeDirectory, entry)),
    ...(options.access === "write" ? [] : [options.directory]),
    ...(options.memoryEnabled ? [] : [memoryDirectory]),
  ].filter((entry) => !extraWritable.includes(entry));
  const writablePaths = [
    ...(options.access === "write" ? [options.directory] : []),
    ...extraWritable,
    path.join(options.homeDirectory, "tmp"),
    ...(options.memoryEnabled ? [memoryDirectory] : []),
  ];
  const tools = options.access === "none"
    ? []
    : options.access === "read"
      ? ["Read", "Glob", "Grep", "Bash", "Skill"]
      : ["Read", "Glob", "Grep", "Bash", "Edit", "Write", "Skill"];
  const settings = {
    disableAllHooks: true,
    autoMemoryEnabled: options.memoryEnabled,
    autoMemoryDirectory: memoryDirectory,
    enabledPlugins: {},
    permissions: {
      blockReadsOutsideWorkingDirectories: true,
      allow: options.access === "none" ? [] : [
        "Bash", "Skill", "Glob", "Grep",
        ...[options.directory, options.homeDirectory].map((entry) => `Read(/${entry}/**)`),
        ...writablePaths.flatMap((entry) => [`Edit(/${entry}/**)`, `Write(/${entry}/**)`]),
      ],
      deny: [
        "Agent", "WebFetch", "WebSearch", "mcp__*", `Read(/${authenticationFile})`, "Bash(security *)",
        ...protectedPaths.flatMap((entry) => [
          `Edit(/${entry})`, `Edit(/${entry}/**)`, `Write(/${entry})`, `Write(/${entry}/**)`,
        ]),
      ],
      additionalDirectories: [options.homeDirectory],
    },
    sandbox: {
      enabled: true,
      failIfUnavailable: true,
      allowUnsandboxedCommands: false,
      autoAllowBashIfSandboxed: true,
      excludedCommands: [],
      filesystem: {
        allowWrite: writablePaths,
        denyRead: [os.homedir(), ...options.blockedPaths, authenticationFile],
        allowRead: [options.directory, options.homeDirectory, ...extraWritable, ...runtimeDirectories],
        denyWrite: protectedPaths,
      },
      network: { allowedDomains: [], allowLocalBinding: false },
    },
  };

  return [
    "claude", "-p", "--output-format", "stream-json", "--verbose",
    "--model", options.model ?? nativeModels["claude-code"], "--effort", options.effort ?? "medium",
    "--permission-mode", "dontAsk",
    ...(options.persistSession || options.resumeSessionId ? [] : ["--no-session-persistence"]),
    ...(options.resumeSessionId ? ["--resume", options.resumeSessionId] : []),
    "--add-dir", options.homeDirectory,
    "--setting-sources", "user,project,local", "--strict-mcp-config",
    "--mcp-config", '{"mcpServers":{}}', "--tools", tools.join(","),
    "--settings", JSON.stringify(settings),
    ...(options.outputSchema ? ["--json-schema", JSON.stringify(options.outputSchema)] : []),
  ];
}
