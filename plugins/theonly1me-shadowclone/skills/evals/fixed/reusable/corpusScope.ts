import { Database, constants } from "bun:sqlite";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { z } from "zod";
import { readConfig, canonicalPath } from "@shadowclone/core";
import { allowlistedSignals } from "@shadowclone/learning";
import { readEnvironment } from "@shadowclone/environment";
import {
  EventIndex,
  type IndexedEvent,
  observeClaudeCodeFile,
  resolveRedacted,
  resolveRepository,
  mineSteeringEpisodes,
  eventOriginKey,
  resolveEventRepositories,
} from "@shadowclone/sessions";
import { correctionSessions } from "./corpus";
import { reusableLayout } from "./environments";

const evidenceSchema = z.object({
  type: z.enum(["assistant", "user"]),
  sessionId: z.string(),
  message: z.object({
    content: z.union([
      z.string(),
      z.array(z.object({ type: z.literal("text"), text: z.string() })),
    ]),
  }),
});

export async function verifiedCorpusRepository(options: {
  directory: string;
  preparation: number;
}) {
  const layout = reusableLayout(options.directory);
  const arm = `deep-${options.preparation}`;
  const paths = layout.paths(arm);
  const config = await readConfig({ configPath: paths.configFile });
  const environment = await readEnvironment(paths);
  const workspace = layout.workspace({ arm, repository: "atlas" });
  const repository = await resolveRepository({
    cwd: workspace,
    enabled: config.sources["git-metadata"],
  });
  if (
    repository.id !== "github.com/synthetic-shadowclone/atlas" ||
    !environment?.repositories.some(
      (entry) =>
        entry.directory === canonicalPath(workspace) &&
        entry.originDirectory === repository.origin.directoryName &&
        entry.repositoryName === repository.profileFileName,
    )
  ) {
    throw new Error(
      "Correction fixture requires the registered synthetic Atlas repository with Git-metadata consent.",
    );
  }
  return repository;
}

export async function validateCorpusScope(options: {
  directory: string;
  preparation: number;
}): Promise<{ sessions: number; events: number; repository: string }> {
  const layout = reusableLayout(options.directory);
  const paths = layout.paths(`deep-${options.preparation}`);
  const repository = await verifiedCorpusRepository(options);
  const journal = Bun.file(`${paths.indexDatabase}-wal`);
  if ((await journal.exists()) && journal.size > 0)
    throw new Error("Correction scope validation requires a checkpointed, inactive index.");
  const index = new EventIndex(
    new Database(
      `${pathToFileURL(paths.indexDatabase).href}?immutable=1`,
      constants.SQLITE_OPEN_READONLY | constants.SQLITE_OPEN_URI,
    ),
  );
  try {
    const events: IndexedEvent[] = [];
    for (const session of correctionSessions) {
      const batch = await observeClaudeCodeFile({
        sourcePath: path.join(
          paths.claudeProjectsDirectory,
          "synthetic-atlas",
          `${session.id}.jsonl`,
        ),
        cursor: null,
      });
      if (batch?.invalidRecords !== 0 || batch.events.length !== session.messages.length)
        throw new Error(
          "Correction fixture must retain every assistant example and user correction.",
        );
      for (const [position, event] of batch.events.entries()) {
        const expected = session.messages[position];
        if (
          !expected ||
          !event.textRef ||
          event.sessionId !== session.id ||
          event.kind !== (expected.role === "assistant" ? "assistant-text" : "user-prompt")
        ) {
          throw new Error("Correction fixture has an ineligible or mismatched evidence reference.");
        }
        const evidence = evidenceSchema.parse(
          JSON.parse(
            await resolveRedacted({ ref: event.textRef, roots: [paths.claudeProjectsDirectory] }),
          ),
        );
        const text =
          typeof evidence.message.content === "string"
            ? evidence.message.content
            : evidence.message.content.map((block) => block.text).join("\n");
        if (
          evidence.type !== expected.role ||
          evidence.sessionId !== session.id ||
          text !== expected.text
        )
          throw new Error("Correction fixture text differs after redacted materialization.");
        events.push({ ...event, id: events.length + 1, sourcePath: batch.sourcePath });
      }
    }
    const repositories = await resolveEventRepositories({
      events,
      enabled: true,
      bindings: {
        getOriginObservationStart: () => index.getOriginObservationStart(),
        getOriginBinding: (key) => index.getOriginBinding(key),
        getSessionOriginBinding: (options) => index.getSessionOriginBinding(options),
        bindOrigin: () => {},
      },
    });
    if (events.some((event) => repositories.get(eventOriginKey(event))?.id !== repository.id))
      throw new Error(
        "Correction fixture scope is unresolved or differs from registered Atlas. No learning calls may start.",
      );
    const episodes = allowlistedSignals({
      signals: mineSteeringEpisodes({ events, repositories }),
      events,
    });
    if (
      episodes.length !== correctionSessions.length ||
      episodes.some((episode) => episode.textRefs.length !== 1 || episode.contextRefs?.length !== 1)
    ) {
      throw new Error(
        "Correction fixture must retain paired assistant context through the learning allowlist.",
      );
    }
    const decoy = await observeClaudeCodeFile({
      sourcePath: path.join(
        paths.claudeProjectsDirectory,
        "synthetic-atlas/excluded-tool-output.jsonl",
      ),
      cursor: null,
    });
    if (
      decoy?.invalidRecords !== 0 ||
      decoy.events.length !== 1 ||
      decoy.events.some((event) => event.kind !== "tool-result" || event.textRef !== null)
    ) {
      throw new Error("Correction fixture must exclude tool-result text from learning.");
    }
    return {
      sessions: correctionSessions.length,
      events: events.length,
      repository: repository.id,
    };
  } finally {
    index.close();
  }
}
