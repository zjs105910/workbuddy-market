import path from "node:path";
import { canonicalPath, type ProjectPaths } from "@shadowclone/core";

export function portableSkillDirectories(options: {
  readonly paths: ProjectPaths;
  readonly name: string;
}): readonly string[] {
  const home = path.dirname(options.paths.shadowcloneDirectory);

  return [
    path.join(home, ".agents/skills", options.name),
    path.join(home, ".claude/skills", options.name),
    path.join(home, ".gemini/config/skills", options.name),
  ].map(canonicalPath);
}

export function redundantSkillDirectories(options: {
  readonly paths: ProjectPaths;
  readonly name: string;
}): readonly string[] {
  return [
    path.join(
      path.dirname(options.paths.codexSessionsDirectory),
      "skills",
      options.name,
    ),
    path.join(
      path.dirname(options.paths.shadowcloneDirectory),
      ".cursor/skills",
      options.name,
    ),
  ].map(canonicalPath);
}
