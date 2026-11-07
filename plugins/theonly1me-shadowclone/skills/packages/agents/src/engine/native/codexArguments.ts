import path from "node:path";
import { realpathSync } from "node:fs";
import { nativeModels, type NativeEngineOptions } from "./types";

export function nativeCodexArguments(options: NativeEngineOptions): string[] {
  const home = options.homeDirectory;
  const runtimeDirectories = ["codex", "node", "bun"].flatMap((name) => {
    const executable = Bun.which(name);

    return executable ? [path.dirname(executable), path.dirname(realpathSync(executable))] : [];
  });
  const permissions = {
    extends: ":read-only",
    filesystem: {
      ":root": "deny",
      ":minimal": "read",
      "/tmp": "deny",
      "/private/tmp": "deny",
      ...Object.fromEntries(runtimeDirectories.map((directory) => [directory, "read"])),
      [options.directory]: options.access === "write" ? "write" : "read",
      [path.join(home, "tmp")]: "write",
      [path.join(home, ".agents")]: "read",
      [path.join(home, ".codex", "AGENTS.md")]: "read",
      [path.join(home, ".codex", "AGENTS.override.md")]: "read",
      [path.join(home, ".codex", "skills")]: "read",
      [path.join(home, ".codex", "memories")]: options.memoryEnabled ? "write" : "deny",
      [path.join(home, ".codex", "auth.json")]: "deny",
      [path.join(options.directory, ".git")]: "deny",
      ...Object.fromEntries((options.writablePaths ?? []).map((entry) => [entry, "write"])),
      ...(options.toolDirectory ? { [options.toolDirectory]: "read" } : {}),
      ...Object.fromEntries(options.blockedPaths.map((entry) => [entry, "deny"])),
      ...Object.fromEntries(options.protectedPaths.map((entry) => [entry, "read"])),
    },
    network: { enabled: false },
  };
  const filesystem = Object.entries(permissions.filesystem)
    .map(([key, value]) => `${JSON.stringify(key)}=${JSON.stringify(value)}`)
    .join(",");
  const environment = {
    HOME: home,
    TMPDIR: path.join(home, "tmp"),
    NX_DAEMON: "false",
    NX_SOCKET_DIR: path.join(home, "tmp", "nx"),
    XDG_CACHE_HOME: path.join(home, "tmp", "cache"),
    NODE_COMPILE_CACHE: path.join(home, "tmp", "node-cache"),
    ...(options.toolDirectory
      ? {
          PATH: [options.toolDirectory, process.env.PATH ?? ""]
            .filter(Boolean)
            .join(path.delimiter),
        }
      : {}),
  };
  const settings = Object.entries(environment)
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(",");

  return [
    "codex",
    "exec",
    ...(options.resumeSessionId
      ? ["resume", options.resumeSessionId, "-", "--json"]
      : ["-", "--json", "-C", options.directory]),
    "--skip-git-repo-check",
    "--ignore-user-config",
    "--ignore-rules",
    "--model",
    options.model ?? options.learningModel ?? nativeModels.codex,
    "-c",
    `model_reasoning_effort="${options.effort ?? "medium"}"`,
    "-c",
    'approval_policy="never"',
    "-c",
    "mcp_servers={}",
    "-c",
    'default_permissions="native-evaluation"',
    "-c",
    `permissions.native-evaluation={extends=${JSON.stringify(permissions.extends)},filesystem={${filesystem}},network={enabled=false}}`,
    "-c",
    `shell_environment_policy={inherit="core",set={${settings}}}`,
    "-c",
    `features.memories=${options.memoryEnabled}`,
    "-c",
    `memories.use_memories=${options.memoryEnabled}`,
    "-c",
    "features.hooks=false",
    "-c",
    "features.skip_host_skill_discovery=false",
    "-c",
    "features.apps=false",
    "-c",
    "features.plugins=false",
    "-c",
    "features.multi_agent_v2=false",
    "-c",
    "features.browser_use=false",
    "-c",
    "features.computer_use=false",
    "-c",
    'web_search="disabled"',
    ...(options.access === "none" ? ["--disable", "shell_tool"] : []),
  ];
}
