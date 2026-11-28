import { expect, test } from "bun:test";
import { lstat, symlink } from "node:fs/promises";
import path from "node:path";
import { readConfig } from "@shadowclone/core";
import { bunTaskList, harnessTestSetup, pythonConfig } from "@shadowclone/harness/testing";
import { readHarnessRoots } from "@shadowclone/harness";
import { init, read, rules } from "./initFixture";
import { undoRevision } from "@shadowclone/environment";

test("init writes the harness once and then finds it up to date", async () => {
  const setup = await harnessTestSetup({
    fixture: bunTaskList,
    globalRules: rules,
  });

  expect(await init(setup)).not.toBeNull();
  expect(await read(setup, "AGENTS.md")).toContain(
    "- Gate: `bun run check`. Run it before presenting any change.",
  );
  expect(await read(setup, "AGENTS.md")).toContain(
    "- Small files: Keep every file under 200 lines, tests included.",
  );
  expect(await read(setup, "CLAUDE.md")).toBe(
    "# Claude instructions\n\n<!-- shadowclone-harness:start -->\n@AGENTS.md\n<!-- shadowclone-harness:end -->\n",
  );
  expect(
    await read(setup, ".claude/skills/feature-workflow/SKILL.md"),
  ).toContain("6. Run `bun run check` and fix every failure.");
  expect(await read(setup, ".agents/skills/feature-workflow/SKILL.md")).toBe(
    await read(setup, ".claude/skills/feature-workflow/SKILL.md"),
  );
  expect(
    await init(setup, {
      personal: null,
      ask: () => {
        throw new Error("asked again");
      },
    }),
  ).toBeNull();
});

test("init asks before reading manifests and does nothing when declined", async () => {
  const setup = await harnessTestSetup({
    fixture: bunTaskList,
    globalRules: rules,
    sources: { "repository-manifests": false },
  });

  expect(await init(setup, { ask: () => false })).toBeNull();
  expect(
    await Bun.file(path.join(setup.root, "AGENTS.md")).exists(),
  ).toBeFalse();
  expect(
    (await readConfig({ configPath: setup.paths.configFile })).sources[
      "repository-manifests"
    ],
  ).toBeFalse();
});

test("an edited managed section is preserved along with text outside it", async () => {
  const setup = await harnessTestSetup({
    fixture: bunTaskList,
    globalRules: rules,
  });

  await Bun.write(
    path.join(setup.root, "AGENTS.md"),
    "# Team notes\n\nUse the shared queue.\n",
  );
  await init(setup);

  const edited = (await read(setup, "AGENTS.md")).replace(
    "Run it before presenting any change.",
    "Run it twice.",
  );

  await Bun.write(path.join(setup.root, "AGENTS.md"), edited);
  await Bun.write(
    path.join(setup.paths.profileDirectory, "global/workflow.md"),
    "## Plans\n\nPlan before editing more than three files.\n",
  );
  await init(setup);

  expect(await read(setup, "AGENTS.md")).toBe(edited);
  expect(edited).toStartWith("# Team notes\n\nUse the shared queue.\n");
  expect(edited).toContain("<!-- shadowclone-harness:start -->");
});

test("personal global rules stay out unless the owner confirms them", async () => {
  const setup = await harnessTestSetup({
    fixture: bunTaskList,
    globalRules: rules,
  });

  await init(setup, { personal: false });

  expect(await read(setup, "AGENTS.md")).not.toContain("Small files");
  expect(
    JSON.parse(await read(setup, ".shadowclone/harness.json")).personal,
  ).toBeFalse();
});

test("a planted profile secret never reaches the committed harness", async () => {
  const secret = ["sk", "live", "0123456789abcdefghij"].join("_");
  const setup = await harnessTestSetup({
    fixture: bunTaskList,
    globalRules: `## Deploy key\n\nNever paste ${secret} into scripts.\n`,
  });

  await init(setup);

  expect(await read(setup, "AGENTS.md")).not.toContain(secret);
  expect(await read(setup, "AGENTS.md")).toContain("[redacted:");
});

test("an existing AGENTS.md import or a symlinked CLAUDE.md is left alone", async () => {
  const imported = await harnessTestSetup({ fixture: bunTaskList });

  await Bun.write(
    path.join(imported.root, "CLAUDE.md"),
    "@AGENTS.md\n\nClaude notes.\n",
  );
  await init(imported);

  expect(await read(imported, "CLAUDE.md")).toBe(
    "@AGENTS.md\n\nClaude notes.\n",
  );

  const linked = await harnessTestSetup({ fixture: bunTaskList });

  await symlink("AGENTS.md", path.join(linked.root, "CLAUDE.md"));
  await init(linked);

  expect(
    (await lstat(path.join(linked.root, "CLAUDE.md"))).isSymbolicLink(),
  ).toBeTrue();
  expect(await read(linked, "AGENTS.md")).toContain(
    "shadowclone-harness:start",
  );
});

test("undo removes a freshly written harness", async () => {
  const setup = await harnessTestSetup({
    fixture: bunTaskList,
    globalRules: rules,
  });
  const revision = await init(setup);

  if (revision === null) {
    throw new Error("Expected a revision");
  }

  await undoRevision({
    paths: setup.paths,
    id: revision,
    harnessRoots: await readHarnessRoots(setup.paths),
  });

  expect(
    await Bun.file(path.join(setup.root, "AGENTS.md")).exists(),
  ).toBeFalse();
  expect(
    await Bun.file(path.join(setup.root, ".shadowclone/harness.json")).exists(),
  ).toBeFalse();
});

test("the Python fixture gets its unittest gate and no Bun rules", async () => {
  const setup = await harnessTestSetup({
    fixture: pythonConfig,
    globalRules: rules,
  });

  await init(setup);

  const agents = await read(setup, "AGENTS.md");

  expect(agents).toContain("- Gate: `python3 -m unittest`.");
  expect(agents).not.toContain("Bun tests");
  expect(agents).toContain("- Small files:");
});
