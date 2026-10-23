import { expect, test } from "bun:test";
import path from "node:path";
import { defaultConfig, writeConfig } from "@shadowclone/core";
import { type BuildContext, environmentCompilation } from "@shadowclone/environment";
import { writeMaintenanceState, loadSeedLibrary } from "@shadowclone/skills";
import { applyBuild } from "./apply";
import { buildCatalog } from "./catalog";
import { buildFixture, buildInput } from "./testing";
import { previewBuild } from "./plan";

const nativeRoutingLimit = 4096;
const userRoutingReserve = 1024;

test("a build with every bundled skill and preference leaves 1 KiB of routing for the user's own rules", async () => {
  const context = await buildFixture();
  const library = await loadSeedLibrary();
  const choices = Object.fromEntries([
    ...library.independentSkills.map((skill) => [skill.id, true] as const),
    ...library.axes.flatMap((axis) =>
      axis.guidance[0] ? [[axis.guidance[0].id, true] as const] : [],
    ),
  ]);

  await applyBuild({
    ...context,
    plan: await previewBuild({ ...context, input: buildInput({ choices }) }),
  });

  const compilation = await environmentCompilation({
    ...context,
    originDirectory: null,
    repositoryName: null,
  });

  expect(Buffer.byteLength(compilation?.markdown ?? "")).toBeLessThanOrEqual(
    nativeRoutingLimit - userRoutingReserve,
  );
  expect(compilation?.markdown).toContain(
    "- before you say that work is done or ready for review: verify-and-review",
  );
});

async function equipPersonalSkills(options: {
  readonly context: BuildContext;
  readonly names: readonly string[];
}): Promise<Record<string, true>> {
  const home = path.dirname(options.context.paths.shadowcloneDirectory);
  const directory = path.join(home, ".agents/skills");

  await writeConfig({
    config: { ...defaultConfig, sources: { ...defaultConfig.sources, "skill-library": true } },
    configPath: options.context.paths.configFile,
  });

  for (const name of options.names) {
    const description = `Use when ${name} work starts. ${"Covers planning, edits, reviews, and handoff for this synthetic workflow. ".repeat(9)}`;

    await Bun.write(
      path.join(directory, name, "SKILL.md"),
      `---\nname: ${name}\ndescription: ${JSON.stringify(description.trim())}\n---\n\nFollow the ${name} steps.\n`,
    );
  }

  await writeMaintenanceState({
    paths: options.context.paths,
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

  const catalog = await buildCatalog({ ...options.context, scope: "global" });

  return Object.fromEntries(
    catalog
      .filter((item) => options.names.includes(item.name))
      .map((item) => [item.id, true] as const),
  );
}

test("personal skills without a moment route by name so a full build fits the routing budget", async () => {
  const context = await buildFixture();
  const library = await loadSeedLibrary();
  const names = [
    "alpha-review",
    "bravo-release",
    "charlie-debug",
    "delta-docs",
    "echo-plan",
    "foxtrot-test",
  ];
  const personal = await equipPersonalSkills({ context, names });
  const choices = Object.fromEntries([
    ...library.independentSkills.map((skill) => [skill.id, true] as const),
    ...library.axes.flatMap((axis) =>
      axis.guidance[0] ? [[axis.guidance[0].id, true] as const] : [],
    ),
    ...Object.entries(personal),
  ]);

  expect(Object.keys(personal)).toHaveLength(names.length);

  await applyBuild({
    ...context,
    plan: await previewBuild({ ...context, input: buildInput({ choices }) }),
  });

  const compilation = await environmentCompilation({
    ...context,
    originDirectory: null,
    repositoryName: null,
  });
  const markdown = compilation?.markdown ?? "";
  const prefix = "- when the task matches the skill's own description: ";
  const routed = markdown.split("\n").find((line) => line.startsWith(prefix));

  expect(routed?.slice(prefix.length).split(", ").toSorted()).toEqual(names);
  expect(markdown).not.toContain("synthetic workflow");
});
