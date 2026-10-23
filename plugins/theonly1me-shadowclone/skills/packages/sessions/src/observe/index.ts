import type { ShadowcloneConfig, ProjectPaths } from "@shadowclone/core";
import {
  discoverAntigravityFiles,
  observeAntigravityFile,
} from "./adapters/antigravity";
import {
  discoverClaudeCodeFiles,
  observeClaudeCodeFile,
} from "./adapters/claudeCode";
import { observeClaudePromptsFile } from "./adapters/claudePrompts";
import { discoverCodexFiles, observeCodexFile } from "./adapters/codex";
import { discoverCursorFiles, observeCursorFile } from "./adapters/cursor";
import { discoverPiFiles, observePiFile } from "./adapters/pi";
import type { CursorLookup, ObservationBatch } from "./types";

export type {
  AgentEvent,
  AgentEventKind,
  CursorLookup,
  FileTextRef,
  FileCursor,
  ObservationBatch,
  SqliteTextRef,
  TextRef,
  ToolCall,
} from "./types";

export {
  parseTextRef,
  textRefKey,
} from "./types";

export { observeClaudeCodeFile } from "./adapters/claudeCode";
export { observePiFile } from "./adapters/pi";
export { isRecord } from "./record";
export { resolveRedacted } from "./redacted";
export { captureRoots } from "./roots";

export {
  parseAntigravityWorkspaceHistory,
  readAntigravityWorkspaceHistory,
  type AntigravityWorkspaceBinding,
  type AntigravityWorkspaceRead,
} from "./antigravityWorkspaces";

export async function* observeAll(options: {
  readonly config: ShadowcloneConfig;
  readonly paths: ProjectPaths;
  readonly getCursor: CursorLookup;
}): AsyncIterable<ObservationBatch> {
  if (options.config.sources.pi) {
    for (const sourcePath of await discoverPiFiles(options.paths.piSessionsDirectory)) {
      const batch = await observePiFile({ sourcePath, cursor: await options.getCursor(sourcePath) });
      if (batch) yield batch;
    }
  }
  if (options.config.sources.antigravity) {
    const sourcePaths = await discoverAntigravityFiles(
      options.paths.antigravityBrainDirectory,
    );

    for (const sourcePath of sourcePaths) {
      const batch = await observeAntigravityFile({
        sourcePath,
        cursor: await options.getCursor(sourcePath),
      });

      if (batch !== null) {
        yield batch;
      }
    }
  }

  if (options.config.sources["claude-code"]) {
    const sourcePaths = await discoverClaudeCodeFiles(
      options.paths.claudeProjectsDirectory,
    );

    for (const sourcePath of sourcePaths) {
      const batch = await observeClaudeCodeFile({
        sourcePath,
        cursor: await options.getCursor(sourcePath),
      });

      if (batch !== null) {
        yield batch;
      }
    }
  }

  if (options.config.sources["claude-prompts"]) {
    const sourcePath = options.paths.claudePromptHistoryFile;
    const batch = await observeClaudePromptsFile({
      sourcePath,
      cursor: await options.getCursor(sourcePath),
    });

    if (batch !== null) {
      yield batch;
    }
  }

  if (options.config.sources.codex) {
    const sourcePaths = await discoverCodexFiles(
      options.paths.codexSessionsDirectory,
    );

    for (const sourcePath of sourcePaths) {
      const batch = await observeCodexFile({
        sourcePath,
        cursor: await options.getCursor(sourcePath),
      });

      if (batch !== null) {
        yield batch;
      }
    }
  }

  if (options.config.sources.cursor) {
    const sourcePaths = await discoverCursorFiles(
      options.paths.cursorChatsDirectory,
    );

    for (const sourcePath of sourcePaths) {
      const batch = await observeCursorFile({
        sourcePath,
        cursor: await options.getCursor(sourcePath),
      });

      if (batch !== null) {
        yield batch;
      }
    }
  }
}
