import { expect, test } from "bun:test";
import { mkdir, mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { HiddenInstructionsError } from "./hiddenInstructions";
import { installIntegration } from "./install";
import { readIntegrations } from "./state";

const teamRules = "# Team rules\n\nRun the full test suite before you push.\n";

async function repository(options: { readonly files: Record<string, string> }) {
  const home = await realpath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-override-")));
  const cwd = path.join(home, "repo");
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });

  await mkdir(cwd, { recursive: true });

  for (const [name, text] of Object.entries(options.files)) {
    await Bun.write(path.join(cwd, name), text);
  }

  const install = () =>
    installIntegration({
      paths,
      configPath: paths.configFile,
      managedConfigPath: null,
      agent: "codex",
      scope: "repository",
      cwd,
    });

  return { paths, cwd, install };
}

test("a codex repository install stops before its override hides a team AGENTS.md", async () => {
  const setup = await repository({ files: { "AGENTS.md": teamRules } });

  await expect(setup.install()).rejects.toEqual(
    new HiddenInstructionsError({
      override: path.join(setup.cwd, "AGENTS.override.md"),
      hidden: path.join(setup.cwd, "AGENTS.md"),
      installed: false,
    }),
  );
  expect(await Bun.file(path.join(setup.cwd, "AGENTS.override.md")).exists()).toBeFalse();
  expect(await Bun.file(path.join(setup.cwd, "AGENTS.md")).text()).toBe(teamRules);
  expect(await readIntegrations(setup.paths)).toEqual([]);
});

test("a repository without a team AGENTS.md still gets the codex override", async () => {
  const setup = await repository({ files: {} });

  await setup.install();

  expect(await Bun.file(path.join(setup.cwd, "AGENTS.override.md")).text()).toContain(
    "<shadowclone-guidance>",
  );
});

test("an override that the user made next to the team file stays the user's choice", async () => {
  const setup = await repository({
    files: { "AGENTS.md": teamRules, "AGENTS.override.md": "# My overrides\n" },
  });

  await setup.install();

  expect(await Bun.file(path.join(setup.cwd, "AGENTS.override.md")).text()).toStartWith(
    "# My overrides\n",
  );
  expect(await Bun.file(path.join(setup.cwd, "AGENTS.md")).text()).toBe(teamRules);
});

test("a reinstall reports an override that Shadowclone created before the team file existed", async () => {
  const setup = await repository({ files: {} });

  await setup.install();
  await Bun.write(path.join(setup.cwd, "AGENTS.md"), teamRules);

  await expect(setup.install()).rejects.toEqual(
    new HiddenInstructionsError({
      override: path.join(setup.cwd, "AGENTS.override.md"),
      hidden: path.join(setup.cwd, "AGENTS.md"),
      installed: true,
    }),
  );
});
