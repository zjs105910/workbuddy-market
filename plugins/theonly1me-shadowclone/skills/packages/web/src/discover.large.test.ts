import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import path from "node:path";
import { buildView } from "./view";
import { discoverDeliverySkills, readMaintenanceState } from "@shadowclone/skills";
import { skillFixture } from "@shadowclone/environment/testing";
import { fixtureSkill } from "@shadowclone/skills/testing";

test("500 skills with native copies and overlapping roots remain discoverable in the browser catalog", async () => {
  const setup = await skillFixture();
  try {
    for (let index = 0; index < 500; index += 1) {
      const name = `palette-${index}`;
      await Promise.all([".agents", ".claude", ".cursor"].map((directory) =>
        Bun.write(path.join(setup.home, directory, "skills", name, "SKILL.md"), fixtureSkill(name))));
    }
    const state = await readMaintenanceState(setup.paths);
    const roots = [...state.roots, ...state.roots];
    const discovery = discoverDeliverySkills(roots);
    await expect(discovery).resolves.toMatchObject({ invalid: 0, duplicates: 0 });
    const discovered = await discovery;
    expect(discovered.skills).toHaveLength(501);
    expect(discovered.invalid).toBe(0);
    expect(discovered.duplicates).toBe(0);
    const view = await buildView({ ...setup, scope: "global", revisionId: null });
    const catalog = view.items;
    expect(catalog.filter((item) => item.name.startsWith("palette-"))).toHaveLength(500);
    const constellation = view.constellation;
    expect(constellation.leaves.flatMap((leaf) => leaf.itemIds)).toEqual(expect.arrayContaining(
      catalog.filter((item) => item.name.startsWith("palette-")).map((item) => item.id)));
    const hubs = new Map(constellation.hubs.map((hub) => [hub.id, hub]));
    expect(constellation.leaves.every((leaf) =>
      hubs.get(hubs.get(leaf.parentId)?.parentId ?? "")?.parentId === null)).toBeTrue();
  } finally {
    await rm(setup.home, { recursive: true, force: true });
  }
}, 15_000);
