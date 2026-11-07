import { expect, test } from "bun:test";
import path from "node:path";
import { runHostCommand } from "@shadowclone/core";
import { integrationFixture } from "@shadowclone/core/testing";
import { installIntegration, uninstallIntegration } from "./install";
import { renderInstructionPointer, updateManagedSection } from "./markdown";
import { readIntegrations, saveIntegration } from "./state";

const teamRules = "# Team rules\n\nRun the full test suite before you push.\n";

async function gitRepository() {
  const fixture = await integrationFixture();

  await runHostCommand({ arguments: ["git", "init", "-q"], cwd: fixture.cwd });

  return fixture;
}

async function gitStatus(cwd: string): Promise<string> {
  return (await runHostCommand({ arguments: ["git", "status", "--porcelain"], cwd })).stdout;
}

test("a Pi repository install leaves the team AGENTS.md untouched", async () => {
  const fixture = await gitRepository();

  await Bun.write(path.join(fixture.cwd, "AGENTS.md"), teamRules);

  const installed = await installIntegration({ ...fixture, agent: "pi", scope: "repository" });

  expect(await Bun.file(path.join(fixture.cwd, "AGENTS.md")).text()).toBe(teamRules);
  expect(installed.files.map((file) => file.relativePath)).toEqual([
    ".pi/extensions/shadowclone.js",
    ".agents/skills/shadowclone-context/SKILL.md",
  ]);
});

test("a reinstall removes the section that an older Pi install wrote into the team file", async () => {
  const fixture = await gitRepository();
  const section = updateManagedSection({ previous: teamRules, body: renderInstructionPointer() });

  await Bun.write(path.join(fixture.cwd, "AGENTS.md"), section.text);
  await saveIntegration({
    paths: fixture.paths,
    integration: {
      id: crypto.randomUUID(),
      agent: "pi",
      scope: "repository",
      directory: fixture.cwd,
      userDirectory: fixture.home,
      codexInstructions: "AGENTS.md",
      files: [
        {
          relativePath: "AGENTS.md",
          kind: "instructions",
          fingerprint: section.fingerprint,
          created: false,
        },
      ],
      excludes: [],
      deliveredAt: null,
    },
  });

  await installIntegration({ ...fixture, agent: "pi", scope: "repository" });

  const [integration] = await readIntegrations(fixture.paths);

  expect(await Bun.file(path.join(fixture.cwd, "AGENTS.md")).text()).toBe(teamRules);
  expect(integration?.files.some((file) => file.relativePath === "AGENTS.md")).toBeFalse();
});

test("an edited section from an older Pi install is kept and the install says why", async () => {
  const fixture = await gitRepository();
  const section = updateManagedSection({ previous: teamRules, body: renderInstructionPointer() });
  const edited = section.text.replace("A session hook", "My own session hook");

  await Bun.write(path.join(fixture.cwd, "AGENTS.md"), edited);
  await saveIntegration({
    paths: fixture.paths,
    integration: {
      id: crypto.randomUUID(),
      agent: "pi",
      scope: "repository",
      directory: fixture.cwd,
      userDirectory: fixture.home,
      codexInstructions: "AGENTS.md",
      files: [
        {
          relativePath: "AGENTS.md",
          kind: "instructions",
          fingerprint: section.fingerprint,
          created: false,
        },
      ],
      excludes: [],
      deliveredAt: null,
    },
  });

  await expect(
    installIntegration({ ...fixture, agent: "pi", scope: "repository" }),
  ).rejects.toThrow("Shadowclone managed content was edited; preserving the file");
  expect(await Bun.file(path.join(fixture.cwd, "AGENTS.md")).text()).toBe(edited);
});

test("repository install files stay out of git status, and uninstall removes their excludes", async () => {
  const fixture = await gitRepository();

  await installIntegration({ ...fixture, agent: "codex", scope: "repository" });
  await installIntegration({ ...fixture, agent: "pi", scope: "repository" });

  const exclude = await Bun.file(path.join(fixture.cwd, ".git/info/exclude")).text();

  expect(exclude.split("\n").filter((line) => line.startsWith("/"))).toEqual([
    "/AGENTS.override.md",
    "/.codex/hooks.json",
    "/.agents/skills/shadowclone-context/SKILL.md",
    "/.pi/extensions/shadowclone.js",
  ]);
  expect(await gitStatus(fixture.cwd)).toBe("?? README.md\n");

  for (const integration of await readIntegrations(fixture.paths)) {
    await uninstallIntegration({ paths: fixture.paths, integration });
  }

  expect(
    (await Bun.file(path.join(fixture.cwd, ".git/info/exclude")).text())
      .split("\n")
      .filter((line) => line.startsWith("/")),
  ).toEqual([]);
  expect(await gitStatus(fixture.cwd)).toBe("?? README.md\n");
});
