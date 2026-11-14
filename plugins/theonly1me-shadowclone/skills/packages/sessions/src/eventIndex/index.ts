import { Database } from "bun:sqlite";
import path from "node:path";
import type { ShadowcloneConfig, ProjectPaths } from "@shadowclone/core";
import { observeAll, readAntigravityWorkspaceHistory } from "../observe";
import { observeClaudeCodeFile } from "../observe/adapters/claudeCode";
import { resolveRepository, type GitRemoteReader } from "../signal";
import { ownedDirectory, ownedFile } from "@shadowclone/core";
import { createSchema } from "./schema";
import { EventIndex } from "./store";
import type { IngestSummary } from "./types";

export { EventIndex } from "./store";

export type {
  CorpusSummary,
  IndexedEvent,
  IngestSummary,
} from "./types";

export async function openEventIndex(
  databasePath: string,
): Promise<EventIndex> {
  if (databasePath !== ":memory:") {
    await ownedDirectory(path.dirname(databasePath));

    for (const suffix of ["", "-wal", "-shm"]) {
      await ownedFile(`${databasePath}${suffix}`);
    }
  }

  const database = new Database(databasePath, { create: true });

  createSchema(database);

  if (databasePath !== ":memory:") {
    for (const suffix of ["", "-wal", "-shm"]) {
      await ownedFile(`${databasePath}${suffix}`);
    }
  }

  return new EventIndex(database);
}

export async function ingestSources(options: {
  readonly index: EventIndex;
  readonly config: ShadowcloneConfig;
  readonly paths: ProjectPaths;
  readonly readRemote?: GitRemoteReader;
}): Promise<IngestSummary> {
  let files = 0;
  let events = 0;
  let bytesRead = 0;
  let rescannedFiles = 0;
  let invalidRecords = 0;

  if (options.config.sources["antigravity-workspaces"]) {
    const history = await readAntigravityWorkspaceHistory(
      options.paths.antigravityWorkspaceHistoryFile,
    );

    if (history !== null) {
      const repositories = new Map<
        string,
        Awaited<ReturnType<typeof resolveRepository>>
      >();

      for (const binding of history.bindings) {
        let repository = repositories.get(binding.workspace);

        if (repository === undefined) {
          repository = await resolveRepository({
            cwd: binding.workspace,
            enabled: options.config.sources["git-metadata"],
            readRemote: options.readRemote,
          });
          repositories.set(binding.workspace, repository);
        }

        options.index.bindSessionOrigin({
          source: "antigravity",
          sessionId: binding.sessionId,
          timestamp: binding.timestamp,
          repository,
        });
      }

      files += 1;
      bytesRead += history.bytesRead;
      invalidRecords += history.invalidRecords;
    }
  }

  for await (const batch of observeAll({
    config: options.config,
    paths: options.paths,
    getCursor: (sourcePath) => options.index.getCursor(sourcePath),
  })) {
    options.index.saveBatch(batch);
    files += 1;
    events += batch.events.length;
    bytesRead += batch.bytesRead;
    rescannedFiles += batch.rescanned ? 1 : 0;
    invalidRecords += batch.invalidRecords;
  }

  return {
    files,
    events,
    sessions: options.index.countSessions(),
    bytesRead,
    rescannedFiles,
    invalidRecords,
  };
}

export async function ingestClaudeTranscript(options: {
  readonly index: EventIndex;
  readonly sourcePath: string;
}): Promise<number> {
  const batch = await observeClaudeCodeFile({
    sourcePath: options.sourcePath,
    cursor: options.index.getCursor(options.sourcePath),
  });

  if (batch === null) {
    return 0;
  }

  options.index.saveBatch(batch);

  return batch.events.length;
}
