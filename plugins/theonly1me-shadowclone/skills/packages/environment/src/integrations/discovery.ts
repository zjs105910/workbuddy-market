import type { IntegrationAgent } from "./types";

export type HostDiscovery = {
  readonly agent: IntegrationAgent;
  readonly skillFolders: readonly string[];
  readonly routing:
    { readonly kind: "instructions"; readonly file: string } | { readonly kind: "session-hook" };
};

export const hostDiscovery: readonly HostDiscovery[] = [
  {
    agent: "claude-code",
    skillFolders: [".claude/skills"],
    routing: { kind: "instructions", file: ".claude/CLAUDE.md" },
  },
  {
    agent: "codex",
    skillFolders: [".agents/skills"],
    routing: { kind: "instructions", file: ".codex/AGENTS.md" },
  },
  {
    agent: "cursor",
    skillFolders: [".agents/skills", ".claude/skills"],
    routing: { kind: "session-hook" },
  },
  {
    agent: "antigravity",
    skillFolders: [".gemini/config/skills"],
    routing: { kind: "session-hook" },
  },
  {
    agent: "pi",
    skillFolders: [".agents/skills"],
    routing: { kind: "instructions", file: ".pi/agent/AGENTS.md" },
  },
];

export const knownDeliveryGaps = [
  {
    id: "private-builds",
    summary: "Private build skills stay under ~/.shadowclone/builds, which no host reads.",
  },
  {
    id: "cursor-duplicate-global-skills",
    summary:
      "Cursor reads ~/.agents/skills and ~/.claude/skills, so each global skill reaches it twice.",
  },
] as const;
