import { expect, test } from "bun:test";
import path from "node:path";
import { applyBuild } from "./apply";
import { buildFixture, buildInput } from "./testing";
import { skillClassification } from "./classification";
import { previewBuild } from "./plan";
import { defaultConfig, writeConfig, seedSkillsDirectory } from "@shadowclone/core";
import { loadSeedLibrary } from "@shadowclone/skills";
import {
  type BuildContext,
  hostDiscovery,
  installIntegration,
  knownDeliveryGaps,
  nativeSessionStart,
} from "@shadowclone/environment";

type DeliveredHome = BuildContext & {
  readonly home: string;
  readonly selected: readonly string[];
};

async function deliveredHome(): Promise<DeliveredHome> {
  const context = await buildFixture();
  const library = await loadSeedLibrary();
  const selected = [
    ...library.independentSkills.map((skill) => skill.id),
    ...library.axes.flatMap((axis) =>
      axis.guidance
        .slice(0, 1)
        .filter((entry) => entry.kind === "skill")
        .map((entry) => entry.id),
    ),
  ].sort();
  const choices = Object.fromEntries(
    library.skills.map((skill) => [skill.id, selected.includes(skill.id)]),
  );

  await writeConfig({ config: defaultConfig, configPath: context.paths.configFile });
  await applyBuild({
    ...context,
    plan: await previewBuild({ ...context, input: buildInput({ choices }) }),
  });

  return { ...context, home: path.dirname(context.paths.shadowcloneDirectory), selected };
}

function stringsIn(value: unknown): readonly string[] {
  if (typeof value === "string") {
    return [value];
  }

  if (Array.isArray(value)) {
    return value.flatMap(stringsIn);
  }

  return value !== null && typeof value === "object" ? Object.values(value).flatMap(stringsIn) : [];
}

async function routingFor(options: {
  readonly delivered: DeliveredHome;
  readonly host: (typeof hostDiscovery)[number];
}): Promise<string> {
  const { delivered, host } = options;
  const installed = await installIntegration({
    paths: delivered.paths,
    configPath: delivered.paths.configFile,
    managedConfigPath: null,
    agent: host.agent,
    scope: "global",
    cwd: delivered.cwd,
  });

  if (host.routing.kind === "instructions") {
    const text = await Bun.file(path.join(delivered.home, host.routing.file)).text();

    return /<shadowclone-guidance>([\s\S]*?)<\/shadowclone-guidance>/.exec(text)?.[1]?.trim() ?? "";
  }

  const output = await nativeSessionStart({
    paths: delivered.paths,
    configPath: delivered.paths.configFile,
    managedConfigPath: null,
    id: installed.id,
    input: JSON.stringify({
      cwd: delivered.cwd,
      workspace_roots: [delivered.cwd],
      workspacePaths: [delivered.cwd],
      conversationId: "matrix",
    }),
  });

  return (
    stringsIn(output)
      .find((text) => text.includes("# Shadowclone guidance"))
      ?.trim() ?? ""
  );
}

test("every host's skill folders receive the bundled bytes of each selected skill", async () => {
  const delivered = await deliveredHome();
  const sourceDirectory = await seedSkillsDirectory();
  const mismatches: string[] = [];

  for (const host of hostDiscovery) {
    for (const folder of host.skillFolders) {
      for (const skill of delivered.selected) {
        const expected = await Bun.file(path.join(sourceDirectory, skill, "SKILL.md")).text();
        const file = Bun.file(path.join(delivered.home, folder, skill, "SKILL.md"));
        const actual = (await file.exists()) ? await file.text() : null;

        if (actual !== expected) {
          mismatches.push(`${host.agent} ${folder}/${skill}`);
        }
      }
    }
  }

  expect(delivered.selected.length).toBeGreaterThan(5);
  expect(mismatches).toEqual([]);
});

test("every host receives the same routing text, and it names each selected skill", async () => {
  const delivered = await deliveredHome();
  const routing = new Map<string, string>();

  for (const host of hostDiscovery) {
    routing.set(host.agent, await routingFor({ delivered, host }));
  }

  const [first = ""] = [...routing.values()];

  expect(
    [...routing.entries()].filter(([, text]) => text !== first).map(([agent]) => agent),
  ).toEqual([]);
  expect(first).toContain(
    "Name every skipped step and every fallback in your final answer and handoff.",
  );

  for (const skill of delivered.selected) {
    const text = await Bun.file(path.join(await seedSkillsDirectory(), skill, "SKILL.md")).text();

    expect(first.split("\n")).toContain(`- ${skillClassification(text).appliesWhen}: ${skill}`);
  }
});

test("the recorded delivery gaps still hold, so closing one means updating the table", async () => {
  const delivered = await deliveredHome();
  const hostFolders = [...new Set(hostDiscovery.flatMap((host) => host.skillFolders))];
  const privateSkill = "private-check";

  await applyBuild({
    ...delivered,
    plan: await previewBuild({
      ...delivered,
      input: buildInput({
        scope: "private",
        custom: [
          {
            name: privateSkill,
            description: "Check the private workflow before handoff.",
            body: "Run the private check and read its output.",
          },
        ],
      }),
    }),
  });

  const privateCopies = await Array.fromAsync(
    new Bun.Glob(`builds/*/skills/${privateSkill}/SKILL.md`).scan({
      cwd: delivered.paths.shadowcloneDirectory,
    }),
  );
  const hostCopies = await Promise.all(
    hostFolders.map((folder) =>
      Bun.file(path.join(delivered.home, folder, privateSkill, "SKILL.md")).exists(),
    ),
  );
  const cursor = hostDiscovery.find((host) => host.agent === "cursor");
  const [firstSkill = ""] = delivered.selected;
  const cursorCopies = await Promise.all(
    (cursor?.skillFolders ?? []).map((folder) =>
      Bun.file(path.join(delivered.home, folder, firstSkill, "SKILL.md")).exists(),
    ),
  );

  expect(knownDeliveryGaps.map((gap) => gap.id)).toEqual([
    "private-builds",
    "cursor-duplicate-global-skills",
  ]);
  expect(privateCopies).toHaveLength(1);
  expect(hostCopies.every((exists) => !exists)).toBeTrue();
  expect(cursorCopies).toEqual([true, true]);
});
