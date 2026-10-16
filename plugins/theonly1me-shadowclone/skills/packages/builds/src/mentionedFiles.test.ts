import { expect, test } from "bun:test";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { writeMaintenanceState } from "@shadowclone/skills";
import { buildCatalog } from "./catalog";
import { buildFixture, buildInput } from "./testing";
import { previewBuild } from "./plan";

test("equipping a user skill that names another skill's file in backticks publishes it", async () => {
  const context = await buildFixture();
  const home = path.dirname(context.paths.shadowcloneDirectory);
  const directory = path.join(home, ".agents/skills");
  const text =
    '---\nname: write-designs\ndescription: "Use when writing a design record."\n---\n\n' +
    "The review skill keeps its tone in `references/voice.md`; this skill does not use it.\n";

  await writeConfig({
    config: { ...defaultConfig, sources: { ...defaultConfig.sources, "skill-library": true } },
    configPath: context.paths.configFile,
  });
  await Bun.write(path.join(directory, "write-designs/SKILL.md"), text);
  await writeMaintenanceState({
    paths: context.paths,
    state: {
      version: 1,
      roots: [
        {
          id: "0".repeat(64),
          directory,
          cwd: home,
          scope: "global",
          owner: "user",
          destination: directory,
          enabled: true,
        },
      ],
      tracked: [],
      assessed: {},
      findings: {},
      rejected: {},
    },
  });

  const item = (await buildCatalog({ ...context, scope: "global" })).find(
    (entry) => entry.name === "write-designs",
  );

  if (!item) throw new Error("The user skill was not offered");

  const plan = await previewBuild({
    ...context,
    input: buildInput({ choices: { [item.id]: true } }),
  });

  expect(plan.updates.map((update) => update.next)).toContain(text);
});
