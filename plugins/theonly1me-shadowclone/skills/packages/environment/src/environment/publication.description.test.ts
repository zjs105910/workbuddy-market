import { expect, test } from "bun:test";
import path from "node:path";
import { rm } from "node:fs/promises";
import { skillFixture } from "./testing";
import { skillPublication } from "./publication";
import { emptyEnvironment } from "./types";
import { synchronizePublishedSkills } from "./synchronize";

test("publication records the validated description and synchronization repairs old metadata", async () => {
  const setup = await skillFixture();

  try {
    const scope = { key: "global", directory: setup.home, repository: null };
    const publication = await skillPublication({
      paths: setup.paths,
      state: emptyEnvironment,
      scope,
      skill: null,
      name: "palette-check",
      text: "---\nname: palette-check\ndescription: Check palettes and exports\n---\n\n# Checks\n\nValidate every export.\n",
      records: [],
    });

    expect(publication.state.artifacts.every(({ description }) =>
      description === "Check palettes and exports",
    )).toBeTrue();

    for (const update of publication.updates) {
      if (update.next !== null) await Bun.write(update.filePath, update.next);
    }

    const state = {
      ...publication.state,
      artifacts: publication.state.artifacts.map((artifact) => ({
        ...artifact,
        description: "Check palettes",
      })),
    };
    const result = await synchronizePublishedSkills({ paths: setup.paths, state });

    expect(result.state.artifacts.every(({ description }) =>
      description === "Check palettes and exports",
    )).toBeTrue();
    expect(await Bun.file(path.join(setup.home, ".agents/skills/palette-check/SKILL.md")).text())
      .toBe(publication.updates[0]?.next ?? "");
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
});
