import { fingerprint } from "@shadowclone/core";
import { scanClaudeMemory } from "@shadowclone/profile";
import type { ProjectPaths } from "@shadowclone/core";
import type { EnvironmentState, LearningRecord } from "@shadowclone/environment";

export async function extractMemoryRecords(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
  readonly enabled: boolean;
}): Promise<EnvironmentState> {
  if (!options.enabled) {
    return options.state;
  }

  const records = new Map(
    options.state.records.map((record) => [record.rule.key, record]),
  );
  const memoryHashes = { ...options.state.memoryHashes };

  for (const repository of options.state.repositories) {
    const files = await scanClaudeMemory({
      paths: options.paths,
      repositoryRoot: repository.directory,
    });

    for (const file of files) {
      if (file.kind === "index") {
        continue;
      }

      const source = `${repository.originDirectory}/${repository.repositoryName}/${file.filename}`;

      if (memoryHashes[source] === file.hash) {
        continue;
      }

      const key = `memory:${fingerprint(source).slice(0, 24)}`;

      const legacy = [...records.values()].find(
        (record) =>
          record.rule.scope === "project" &&
          record.rule.originDirectory === repository.originDirectory &&
          record.rule.repositoryName === repository.repositoryName &&
          (record.rule.key ===
            `claude-memory:${file.filename.replace(/\.md$/, "")}` ||
            record.sourceLocator === file.filename ||
            record.sourceLocator === source),
      );

      const record: LearningRecord = {
        kind:
          file.kind === "feedback" || file.kind === "user"
            ? "guidance"
            : "context",
        sourceHash: file.hash,
        captureSources: ["claude-memory"],
        provenanceComplete: true,
        sourceLocator: source,
        rule: {
          key: legacy?.rule.key ?? key,
          title: file.description || file.name || file.filename,
          body: file.body,
          scope: "project",
          originDirectory: repository.originDirectory,
          repositoryName: repository.repositoryName,
          section: "workflow",
          source: "user",
          status: "active",
          proposal: null,
          appliesWhen: [],
          evidence: { for: [], against: [] },
          observations: 1,
          sessions: 1,
          lastSeen: file.modified || "memory",
          origins: [],
          importReference: null,
        },
      };

      records.set(record.rule.key, record);
      memoryHashes[source] = file.hash;
    }
  }

  return { ...options.state, records: [...records.values()], memoryHashes };
}
