import { mkdir } from "node:fs/promises";
import path from "node:path";
import { initialize } from "@shadowclone/cli";
import { readConfig, writeConfig, createProjectPaths, ownedWrite } from "@shadowclone/core";
import {
  installIntegration,
  registerWorkingRepository,
  syncLearningEnvironment,
} from "@shadowclone/environment";
import { captureArm } from "../../native/study/prepare/freeze";
import { git } from "../../native/study/git";
import type { ArmEnvironment } from "../../native/study/schema";
import { fingerprint } from "../../shared/structured";
import { repositoryInstructions } from "./definition";
import { correctionSessions, excludedCorpusDecoy } from "./corpus";
import { existingManualSkill, intendedAtlasSkill, intendedGlobalSkill } from "./guidance";
import { routingLibrary, routingSkill } from "./routing";
import { parseSkillDocument } from "@shadowclone/skills";
import { openEventIndex } from "@shadowclone/sessions";
import { correctionRepositoryHistory } from "./corpus";
import { verifiedCorpusRepository } from "./corpusScope";

export function reusableLayout(directory: string) {
  const home = (arm: string) => path.join(directory, "homes", arm);
  const workspace = (options: { arm: string; repository: string }) =>
    path.join(directory, "workspaces", options.arm, options.repository);
  return {
    home,
    workspace,
    paths: (arm: string) =>
      createProjectPaths({ homeDirectory: home(arm), platform: process.platform }),
  };
}

export async function prepareManualEnvironment(options: {
  directory: string;
  arm: string;
  routed: boolean;
  told?: boolean;
  routingLibrary?: boolean;
}) {
  const layout = reusableLayout(options.directory);
  const home = layout.home(options.arm);
  for (const repository of ["atlas", "boreal"]) {
    const workspace = layout.workspace({ arm: options.arm, repository });
    await mkdir(workspace, { recursive: true, mode: 0o700 });
    await ownedWrite({ path: path.join(workspace, "AGENTS.md"), content: repositoryInstructions });
    await ownedWrite({ path: path.join(workspace, "CLAUDE.md"), content: "@AGENTS.md\n" });
    await git({ directory: workspace, arguments: ["init", "--quiet"] });
    await git({
      directory: workspace,
      arguments: [
        "config",
        "remote.origin.url",
        `https://github.com/synthetic-shadowclone/${repository}.git`,
      ],
    });
  }
  for (const root of [".agents", ".claude"]) {
    const writeSkill = async (options: { name: string; content: string }) =>
      ownedWrite({
        path: path.join(home, root, "skills", options.name, "SKILL.md"),
        content: options.content,
      });
    if (options.routingLibrary) {
      for (const skill of routingLibrary)
        await writeSkill({ name: skill.name, content: routingSkill(skill) });
    } else {
      await writeSkill({ name: "personal-engineering", content: existingManualSkill });
      if (options.told) {
        await writeSkill({ name: "personal-workflow", content: intendedGlobalSkill });
        await ownedWrite({
          path: path.join(
            layout.workspace({ arm: options.arm, repository: "atlas" }),
            root,
            "skills/atlas-engineering/SKILL.md",
          ),
          content: intendedAtlasSkill,
        });
      }
    }
  }
  if (!options.routed) return;
  const paths = layout.paths(options.arm);
  const workingDirectory = layout.workspace({ arm: options.arm, repository: "atlas" });
  await initialize({
    paths,
    workingDirectory,
    agents: [],
    consent: { learn: false, skills: true, background: false },
    presence: { hasRepositoryGuidance: true, presentCaptureSources: new Set() },
    runner: async () => {
      throw new Error("Offline routing preparation cannot make model calls");
    },
    writeLine: () => {},
  });
  const config = await readConfig({ configPath: paths.configFile });
  await writeConfig({
    configPath: paths.configFile,
    config: { ...config, sources: { ...config.sources, "git-metadata": true } },
  });
  for (const repository of ["atlas", "boreal"]) {
    const cwd = layout.workspace({ arm: options.arm, repository });
    await registerWorkingRepository({
      paths,
      workingDirectory: cwd,
      gitMetadataEnabled: true,
      blockedOrigins: [],
      managedConfigPath: null,
    });
  }
  for (const agent of ["codex", "claude-code"] as const)
    await installIntegration({ paths, agent, scope: "global", cwd: workingDirectory });
  await syncLearningEnvironment(paths);
}

export async function captureEnvironment(options: {
  directory: string;
  arm: string;
  repository: string;
  engine: "codex" | "claude-code";
}) {
  const layout = reusableLayout(options.directory);
  return captureArm({
    home: layout.home(options.arm),
    sourceHome: layout.home(options.arm),
    workspace: layout.workspace(options),
    engine: options.engine,
  });
}

export function requireManualPreserved(options: {
  original: ArmEnvironment;
  candidate: ArmEnvironment;
  allowPublishedAdditions?: boolean;
}) {
  const manual = options.original.files.filter((file) =>
    /\/(?:personal-engineering|[^/]+-contracts)\/SKILL\.md$/.test(file.path),
  );
  for (const source of manual) {
    const actual = options.candidate.files.find(
      (file) => file.root === source.root && file.path === source.path,
    );
    if (!actual) throw new Error("Evaluation preparation changed a manual skill.");
    if (fingerprint(actual) === fingerprint(source)) continue;
    if (
      options.allowPublishedAdditions &&
      actual.encoding === "utf8" &&
      source.encoding === "utf8" &&
      actual.mode === source.mode
    ) {
      const original = parseSkillDocument(source.content);
      const candidate = parseSkillDocument(actual.content);
      const { description: originalDescription, ...originalMetadata } = original.metadata;
      const { description: candidateDescription, ...candidateMetadata } = candidate.metadata;
      if (
        originalDescription &&
        candidateDescription &&
        fingerprint(originalMetadata) === fingerprint(candidateMetadata) &&
        candidate.body.startsWith(original.body.trimEnd())
      )
        continue;
    }
    throw new Error("Evaluation preparation changed a manual skill.");
  }
}

export async function materializeCorpus(options: { directory: string; preparation: number }) {
  const arm = `deep-${options.preparation}`;
  const layout = reusableLayout(options.directory);
  const paths = layout.paths(arm);
  const repository = await verifiedCorpusRepository({
    directory: options.directory,
    preparation: options.preparation,
  });
  const index = await openEventIndex(paths.indexDatabase);
  try {
    if (index.countEvents() !== 0)
      throw new Error("Correction fixtures require a fresh, unlearned index.");
    for (const observation of correctionRepositoryHistory)
      index.bindSessionOrigin({
        source: observation.source,
        sessionId: observation.sessionId,
        timestamp: observation.observedAt,
        repository,
      });
  } finally {
    index.close();
  }
  for (const session of correctionSessions) {
    const observation = correctionRepositoryHistory.find((entry) => entry.sessionId === session.id);
    if (!observation) throw new Error("Correction fixture lacks repository history.");
    const records = session.messages.map((message, index) => ({
      type: message.role,
      sessionId: session.id,
      uuid: `${session.id}-${index}`,
      timestamp: new Date(observation.observedAt + index * 60000).toISOString(),
      cwd: layout.workspace({ arm, repository: "atlas" }),
      message: {
        content:
          message.role === "assistant" ? [{ type: "text", text: message.text }] : message.text,
      },
    }));
    await ownedWrite({
      path: path.join(paths.claudeProjectsDirectory, "synthetic-atlas", `${session.id}.jsonl`),
      content: `${records.map((record) => JSON.stringify(record)).join("\n")}\n`,
    });
  }
  await ownedWrite({
    path: path.join(paths.claudeProjectsDirectory, "synthetic-atlas", "excluded-tool-output.jsonl"),
    content: `${JSON.stringify({
      type: "user",
      sessionId: "excluded-tool-output",
      uuid: "excluded-tool-output-0",
      timestamp: "2026-09-15T10:00:00Z",
      cwd: layout.workspace({ arm, repository: "atlas" }),
      message: { content: [excludedCorpusDecoy] },
    })}\n`,
  });
}
