import path from "node:path";
import type { InstalledArtifact } from "./installState";

export const artifactRelativePaths: Readonly<
  Record<InstalledArtifact, string>
> = {
  agent: path.join(".claude", "agents", "shadowclone.md"),
  "delegation-skill": path.join(".claude", "skills", "shadowclone", "SKILL.md"),
};

export const artifactExcludePatterns: Readonly<
  Record<InstalledArtifact, string>
> = {
  agent: ".claude/agents/shadowclone.md",
  "delegation-skill": ".claude/skills/shadowclone/",
};
