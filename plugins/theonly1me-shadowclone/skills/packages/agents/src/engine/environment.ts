import type { EngineId } from "./types";

const baseKeys = [
  "PATH",
  "HOME",
  "USER",
  "LOGNAME",
  "SHELL",
  "TERM",
  "TMPDIR",
  "LANG",
  "LC_ALL",
  "TZ",
  "SSL_CERT_FILE",
  "NODE_EXTRA_CA_CERTS",
] as const;

const engineKeys: Readonly<Record<EngineId, readonly string[]>> = {
  "claude-code": [
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
  ],
  codex: ["OPENAI_API_KEY", "OPENAI_BASE_URL"],
  "cursor-agent": ["CURSOR_API_KEY"],
  pi: ["PI_CODING_AGENT_DIR"],
  antigravity: ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
  "anthropic-api": ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"],
  "openai-compatible": ["OPENAI_API_KEY", "OPENAI_BASE_URL"],
};

export function runnerEnvironment(options: {
  readonly engine: EngineId;
  readonly source?: Readonly<Record<string, string | undefined>>;
}): Record<string, string> {
  const source = options.source ?? process.env;
  if (options.engine === "pi") {
    return Object.fromEntries(Object.entries(source).filter((entry): entry is [string, string] => entry[1] !== undefined));
  }
  const keys = engineKeys[options.engine];
  const environment: Record<string, string> = {};

  for (const [key, value] of Object.entries(source)) {
    if (value === undefined) {
      continue;
    }

    const isBase = baseKeys.some((baseKey) => baseKey === key);
    const isEngine = keys.includes(key);
    if (isBase || isEngine) {
      environment[key] = value;
    }
  }

  return environment;
}
