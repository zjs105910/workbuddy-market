import type { EngineRunOptions } from "./types";

export function missingClaudeSandboxTools(options: {
  readonly platform: NodeJS.Platform;
  readonly which: (name: string) => string | null;
}): readonly string[] {
  return options.platform === "linux"
    ? ["bwrap", "socat"].filter((name) => options.which(name) === null)
    : [];
}

const emptyMcpArguments = [
  "--strict-mcp-config",
  "--mcp-config",
  '{"mcpServers":{}}',
] as const;

const metadataHosts = [
  "169.254.169.254",
  "metadata.google.internal",
  "metadata.azure.com",
] as const;

function reviewIsolationArguments(run: EngineRunOptions): readonly string[] {
  const tools = run.allowedTools ?? [];
  const network = run.execution.purpose === "review" && run.execution.network === true;
  const settingsJson = JSON.stringify({
    disableAllHooks: true,
    autoMemoryEnabled: false,
    permissions: {
      allow: tools,
      deny: [
        "Bash",
        "Edit",
        "Write",
        "NotebookEdit",
        "mcp__*",
        ...(network
          ? metadataHosts.map((host) => `WebFetch(domain:${host})`)
          : ["WebFetch", "WebSearch"]),
      ],
    },
  });

  return [
    "--safe-mode",
    "--restricted",
    "--no-session-persistence",
    ...emptyMcpArguments,
    "--tools",
    tools.join(","),
    "--disallowedTools",
    "mcp__*",
    "--settings",
    settingsJson,
  ];
}

export function claudeIsolationArguments(
  run: EngineRunOptions,
): readonly string[] {
  if (run.execution.purpose === "review") {
    return reviewIsolationArguments(run);
  }

  const noTools =
    run.execution.purpose === "learning" || run.allowedTools?.length === 0;
  const tools = noTools
    ? ""
    : (
        run.allowedTools ?? ["Read", "Edit", "Write", "Glob", "Grep", "Bash"]
      ).join(",");
  const settingsJson = JSON.stringify({
    ...(run.thinking === "off" ? { env: { MAX_THINKING_TOKENS: "0" } } : {}),
    disableAllHooks: true,
    autoMemoryEnabled: false,
    sandbox: {
      enabled: true,
      failIfUnavailable: true,
      allowUnsandboxedCommands: false,
      autoAllowBashIfSandboxed: true,
      excludedCommands: [],
      filesystem: {
        allowWrite: [run.cwd],
        denyWrite: [
          "**/.git/**",
          "**/.claude/**",
          "**/.codex/**",
          "**/.mcp.json",
        ],
        denyRead: [],
      },
      network: {
        allowedDomains: [],
        allowLocalBinding: false,
      },
    },
    permissions: {
      allow: noTools
        ? []
        : (run.allowedTools ?? ["Read", "Edit", "Write", "Glob", "Grep"]),
      deny: ["WebFetch", "WebSearch", "Agent", "mcp__*"],
    },
  });

  return [
    "--safe-mode",
    "--no-session-persistence",
    ...emptyMcpArguments,
    "--tools",
    tools,
    "--disallowedTools",
    "mcp__*",
    "--settings",
    settingsJson,
  ];
}
