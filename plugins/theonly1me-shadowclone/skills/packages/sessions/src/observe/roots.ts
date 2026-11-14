import type { ProjectPaths } from "@shadowclone/core";

export function captureRoots(paths: ProjectPaths): readonly string[] {
  return [
    paths.antigravityBrainDirectory,
    paths.claudeProjectsDirectory,
    paths.claudePromptHistoryFile,
    paths.codexSessionsDirectory,
    paths.cursorChatsDirectory,
    paths.piSessionsDirectory,
  ];
}
