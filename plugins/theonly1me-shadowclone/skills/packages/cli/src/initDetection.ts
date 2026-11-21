import { opendir } from "node:fs/promises";
import path from "node:path";
import { detectEngine } from "@shadowclone/agents";
import { type IntegrationAgent, integrationAgentSchema } from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";
import type {
  OnboardingCaptureSourceId,
  OnboardingPresence,
} from "./onboardingPresence";

const agentNames: Record<IntegrationAgent, string> = {
  "claude-code": "Claude Code",
  codex: "Codex",
  cursor: "Cursor",
  antigravity: "Antigravity",
  pi: "Pi",
};

async function directoryHasEntry(directoryPath: string): Promise<boolean> {
  try {
    const directory = await opendir(directoryPath);

    try {
      return (await directory.read()) !== null;
    } finally {
      await directory.close();
    }
  } catch {
    return false;
  }
}

export async function detectedIntegrationAgents(
  paths: ProjectPaths,
): Promise<readonly IntegrationAgent[]> {
  const availability = (await detectEngine({ purpose: "distill" }))
    .availability;
  const detected = availability.flatMap((entry) => {
    const agent = integrationAgentSchema.safeParse(
      entry.engine === "cursor-agent" ? "cursor" : entry.engine,
    );

    return entry.installed && agent.success ? [agent.data] : [];
  });
  const homeDirectory = path.dirname(paths.shadowcloneDirectory);
  const antigravity = await Promise.all([
    directoryHasEntry(path.join(homeDirectory, ".gemini", "antigravity-cli")),
    directoryHasEntry(path.join(homeDirectory, ".antigravity-ide")),
  ]);

  return antigravity.some(Boolean) ? [...detected, "antigravity"] : detected;
}

export async function detectPersonalSkills(
  paths: ProjectPaths,
): Promise<boolean> {
  const homeDirectory = path.dirname(
    path.dirname(paths.claudeProjectsDirectory),
  );

  return directoryHasEntry(path.join(homeDirectory, ".claude", "skills"));
}

function detectedSourcePaths(options: {
  readonly paths: ProjectPaths;
  readonly presence: OnboardingPresence;
}): readonly string[] {
  const sourcePaths: Record<OnboardingCaptureSourceId, readonly string[]> = {
    antigravity: [options.paths.antigravityBrainDirectory],
    "claude-code": [options.paths.claudeProjectsDirectory],
    "claude-prompts": [options.paths.claudePromptHistoryFile],
    codex: [options.paths.codexSessionsDirectory],
    cursor: [options.paths.cursorChatsDirectory],
    pi: [options.paths.piSessionsDirectory],
  };
  const homeDirectory = path.dirname(
    path.dirname(options.paths.claudeProjectsDirectory),
  );

  return [...options.presence.presentCaptureSources].flatMap((source) =>
    sourcePaths[source].map((sourcePath) =>
      displayPath({ homeDirectory, sourcePath }),
    ),
  );
}

function displayPath(options: {
  readonly homeDirectory: string;
  readonly sourcePath: string;
}): string {
  return options.sourcePath.startsWith(options.homeDirectory)
    ? `~${options.sourcePath.slice(options.homeDirectory.length)}`
    : options.sourcePath;
}

export function printDetectionSummary(options: {
  readonly paths: ProjectPaths;
  readonly presence: OnboardingPresence;
  readonly agents: readonly IntegrationAgent[];
  readonly personalSkillsPresent: boolean;
  readonly writeLine: (line: string) => void;
}): void {
  const agentList = options.agents.map((agent) => agentNames[agent]);

  options.writeLine(
    `Found  ${agentList.length > 0 ? agentList.join(", ") : "No supported agents"}`,
  );

  if (options.personalSkillsPresent) {
    options.writeLine("       Personal skills in ~/.claude/skills");
  }

  if (options.presence.hasRepositoryGuidance) {
    options.writeLine("       Repository agent guidance");
  }

  const paths = detectedSourcePaths(options);
  const homeDirectory = path.dirname(
    path.dirname(options.paths.claudeProjectsDirectory),
  );
  const codexHome = path.dirname(options.paths.codexSessionsDirectory);
  const codexPath = displayPath({ homeDirectory, sourcePath: codexHome });

  options.writeLine("");
  options.writeLine(
    `Reads  ${paths.length > 0 ? paths.join(", ") : "No session sources detected"}`,
  );
  options.writeLine(
    "       Git remote names; ./CLAUDE.md, ./AGENTS.md, ./.cursorrules, ./.claude/skills, ./.agents/skills",
  );
  options.writeLine(
    `       Agent context: ~/.claude/CLAUDE.md, ${codexPath}/AGENTS.md, ${codexPath}/AGENTS.override.md`,
  );
  options.writeLine(
    `       Agent memories: ~/.claude/projects/<repo>/memory, ${codexPath}/memories`,
  );
  options.writeLine(
    "       Optional Claude migration: exact current-repository ~/.claude/projects/<repo>/memory",
  );
  options.writeLine(
    "       Optional Antigravity attribution: ~/.gemini/antigravity-cli/history.jsonl",
  );
  options.writeLine(
    `       Skills: ~/.claude/skills, ~/.agents/skills, ${codexPath}/skills, ~/.cursor/skills, ~/.gemini/config/skills`,
  );
  options.writeLine(
    `       Plugin caches: ~/.claude/plugins/cache, ${codexPath}/plugins/cache, ~/.cursor/plugins/cache`,
  );
  options.writeLine(
    "       Everything stays on this machine except redacted excerpts sent through your agent CLI.",
  );
}

export function detectedAgentNames(
  agents: readonly IntegrationAgent[],
): string {
  return agents.map((agent) => agentNames[agent]).join(", ");
}
