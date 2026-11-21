import { expect, test } from "bun:test";
import { mkdir, mkdtemp, readlink, realpath, rm, symlink } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { installedBuild } from "./syncFixtures";
import {
  installIntegration,
  readIntegrations,
  saveIntegration,
  syncLearningEnvironment,
  updateManagedSection,
} from "@shadowclone/environment";
import type { ProjectPaths } from "@shadowclone/core";

const olderBody = "# Shadowclone guidance\n\n- when testing: an-old-skill\n";

async function recordOlderSection(options: {
  readonly paths: ProjectPaths;
  readonly agent: "claude-code" | "codex";
  readonly fingerprint: string;
}): Promise<void> {
  const integration = (await readIntegrations(options.paths)).find((entry) => entry.agent === options.agent);

  if (!integration) throw new Error(`The ${options.agent} integration was not installed`);

  await saveIntegration({
    paths: options.paths,
    integration: {
      ...integration,
      files: integration.files.map((file) =>
        file.kind === "instructions" ? { ...file, fingerprint: options.fingerprint } : file,
      ),
    },
  });
}

async function linkedCodexInstructions(options: { readonly outsideHome: boolean }) {
  const setup = await installedBuild();

  await installIntegration({ paths: setup.paths, cwd: setup.cwd, agent: "claude-code", scope: "global" });
  await installIntegration({ paths: setup.paths, cwd: setup.cwd, agent: "codex", scope: "global" });

  const claude = path.join(setup.home, ".claude/CLAUDE.md");
  const codex = path.join(setup.home, ".codex/AGENTS.md");
  const shared = options.outsideHome
    ? path.join(await realpath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-outside-"))), "AGENTS.md")
    : path.join(setup.home, ".agents/AGENTS.md");
  const older = updateManagedSection({ previous: "# My instructions\n", body: olderBody });

  await mkdir(path.dirname(shared), { recursive: true });
  await Bun.write(shared, older.text);
  await rm(codex);
  await symlink(shared, codex);
  await recordOlderSection({ paths: setup.paths, agent: "codex", fingerprint: older.fingerprint });

  return { ...setup, claude, codex, shared, sharedText: older.text };
}

test("sync writes the routing block into the home file that a linked instruction file points to", async () => {
  const setup = await linkedCodexInstructions({ outsideHome: false });

  expect(await syncLearningEnvironment(setup.paths)).toBeTrue();

  const shared = await Bun.file(setup.shared).text();

  expect(shared.startsWith("# My instructions\n")).toBeTrue();
  expect(shared).toContain(": verify-and-review");
  expect(shared).not.toContain("an-old-skill");
  expect(await readlink(setup.codex)).toBe(setup.shared);
  expect(await Bun.file(setup.claude).text()).toContain("<shadowclone-guidance>");
});

test("Claude Code gets no second block when CLAUDE.md imports the file that Codex links to", async () => {
  const setup = await linkedCodexInstructions({ outsideHome: false });

  await Bun.write(setup.claude, `@~/.agents/AGENTS.md\n${await Bun.file(setup.claude).text()}`);

  expect(await syncLearningEnvironment(setup.paths)).toBeTrue();

  const claude = await Bun.file(setup.claude).text();

  expect(claude).toBe("@~/.agents/AGENTS.md\n");
  expect(await Bun.file(setup.shared).text()).toContain(": verify-and-review");

  await syncLearningEnvironment(setup.paths);

  expect(await Bun.file(setup.claude).text()).toBe(claude);
});

test("sync skips and reports a linked instruction file whose target is outside the home folder", async () => {
  const setup = await linkedCodexInstructions({ outsideHome: true });
  const skipped: unknown[] = [];

  await expect(syncLearningEnvironment(setup.paths)).rejects.toThrow(
    "Destination must be a regular file without symbolic links",
  );
  expect(await syncLearningEnvironment(setup.paths, { onSkipped: (entries) => skipped.push(...entries) })).toBeTrue();
  expect(skipped).toEqual([{ agent: "codex", path: setup.codex, target: setup.shared }]);
  expect(await Bun.file(setup.shared).text()).toBe(setup.sharedText);
  expect(await readlink(setup.codex)).toBe(setup.shared);
});
