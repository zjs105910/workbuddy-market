import { expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { z } from "zod";
import { listRevisions } from "@shadowclone/changes";
import { readConfig, writeConfig, canonicalPath, createProjectPaths } from "@shadowclone/core";
import { createLearningExecution, type EngineRunner } from "@shadowclone/agents";
import { initialize } from "./init";
import {
  compileContext,
  installIntegration,
  readEnvironment,
  refreshIntegrations,
  registerWorkingRepository,
  undoRevision,
} from "@shadowclone/environment";
import { publishReviewedLearning, rememberPreference } from "@shadowclone/learning";
import { skillEngineRun } from "@shadowclone/environment/testing";

const globalGuidance = "For readiness checks, set the global readiness code to GLOBAL_PINEAPPLE.";
const repositoryGuidance = "For readiness checks in this repository, set the repository readiness code to REPOSITORY_MAPLE.";

for (const agent of ["claude-code", "codex"] as const) {
  test(`${agent} publishes scoped preferences and undo restores native instructions`, async () => {
    const home = canonicalPath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-delivery-")));
    const cwd = path.join(home, "repository");
    const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
    await mkdir(cwd);
    const readRemote = async () => "https://github.com/synthetic/readiness.git";
    const options = { paths, cwd, readRemote, managedConfigPath: null };
    try {
      await initialize({ paths, workingDirectory: cwd, agents: [], managedConfigPath: null,
        consent: { learn: false, skills: true, background: false }, writeLine: () => {} });
      const config = await readConfig({ configPath: paths.configFile });
      await writeConfig({ configPath: paths.configFile, config: {
        ...config, sources: { ...config.sources, "git-metadata": true }, distillation: { deep: true, automatic: false },
      } });
      await registerWorkingRepository({ ...options, workingDirectory: cwd, gitMetadataEnabled: true, blockedOrigins: [] });
      const globalFile = path.join(home, agent === "claude-code" ? ".claude/CLAUDE.md" : ".codex/AGENTS.md");
      const localFile = path.join(cwd, agent === "claude-code" ? "CLAUDE.local.md" : "AGENTS.override.md");
      for (const file of [globalFile, localFile]) await Bun.write(file, "Preserve this manually authored instruction.\n");
      for (const scope of ["global", "repository"] as const) await installIntegration({ ...options, agent, scope });
      const before = await Promise.all([globalFile, localFile].map((file) => Bun.file(file).text()));
      const previous = new Set((await listRevisions(paths)).map(({ id }) => id));
      const keys = [
        await rememberPreference({ ...options, scope: "global", text: globalGuidance }),
        await rememberPreference({ ...options, scope: "repository", text: repositoryGuidance }),
      ];
      const runner: EngineRunner = async (run) => {
        const input = z.object({ learnings: z.array(z.object({ key: z.string(), text: z.string() })) }).parse(
          JSON.parse(run.prompt.split("\n\n").at(-1) ?? "null"));
        return skillEngineRun(run.prompt.includes("Organize durable user learning")
          ? { routes: input.learnings.map(({ key }) => ({ key, destination: "baseline", skillId: "", name: "shadowclone-baseline",
            description: "Readiness preferences", reason: "Explicit standing preference" })) }
          : { body: "", description: "", edits: input.learnings.map(({ key, text }) => ({ before: "", after: text, keys: [key] })),
            outcomes: input.learnings.map(({ key }) => ({ key, disposition: "apply", reason: "Preserves the explicit instruction" })) });
      };
      expect(await publishReviewedLearning({ ...options, keys, execution: createLearningExecution({ engine: "claude-code", runner }) }))
        .toEqual({ applied: 2, pending: 0 });
      const global = await Bun.file(globalFile).text();
      const repository = await Bun.file(localFile).text();
      expect(global).toContain(globalGuidance);
      expect(global).not.toContain(repositoryGuidance);
      expect(repository).toContain(repositoryGuidance);
      expect(repository).toContain("Preserve this manually authored instruction.");
      expect(await compileContext({ ...options, readRemote: async () => "https://github.com/synthetic/another.git" }))
        .not.toContain(repositoryGuidance);
      const revisions = (await listRevisions(paths)).filter(({ id }) => !previous.has(id));
      expect(revisions.length).toBeGreaterThan(0);
      for (const revision of revisions) await undoRevision({ paths, id: revision.id });
      await refreshIntegrations(options);
      expect(await Promise.all([globalFile, localFile].map((file) => Bun.file(file).text()))).toEqual(before);
      expect((await readEnvironment(paths))?.records).toHaveLength(0);
    } finally {
      await rm(home, { recursive: true, force: true });
    }
  });
}
