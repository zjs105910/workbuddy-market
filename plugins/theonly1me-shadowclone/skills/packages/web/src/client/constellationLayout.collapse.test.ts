import { expect, test } from "bun:test";
import { buildConstellation } from "@shadowclone/builds/browser";
import { syntheticLibrary } from "./constellationFixtures";
import { layoutConstellation, mapMetrics } from "./constellationLayout";

const constellation = buildConstellation(syntheticLibrary({ count: 70 }));
const width = 1440;
const expanded = layoutConstellation({ constellation, width });

function largestCategory() {
  const [category] = constellation.hubs
    .filter((hub) => hub.parentId !== null)
    .map((hub) => ({ hub, members: constellation.leaves.filter((leaf) => leaf.parentId === hub.id) }))
    .sort((left, right) => right.members.length - left.members.length);

  if (!category) throw new Error("The fixture has no category");

  return category;
}

test("a collapsed category hides its skills, counts them, and keeps every other skill", () => {
  const category = largestCategory();
  const layout = layoutConstellation({ constellation, width, collapsed: new Set([category.hub.id]) });
  const skills = layout.nodes.filter((node) => node.kind === "skill");

  expect(skills).toHaveLength(constellation.leaves.length - category.members.length);
  expect(skills.some((node) => node.parentId === category.hub.id)).toBeFalse();
  expect(layout.nodes.find((node) => node.id === category.hub.id)?.hidden).toBe(category.members.length);
  expect(layout.height).toBeLessThanOrEqual(expanded.height);
});

test("a collapsed source hides its categories and leaves room before the next source", () => {
  const [first, second] = constellation.hubs.filter((hub) => hub.parentId === null);

  if (!first || !second) throw new Error("The fixture needs two sources");

  const layout = layoutConstellation({ constellation, width, collapsed: new Set([first.id]) });
  const categoryIds = new Set(constellation.hubs.filter((hub) => hub.parentId === first.id).map((hub) => hub.id));
  const firstNode = layout.nodes.find((node) => node.id === first.id);
  const secondNode = layout.nodes.find((node) => node.id === second.id);
  const nextCategories = layout.nodes.filter((node) => node.parentId === second.id);

  expect(layout.nodes.some((node) => categoryIds.has(node.id) || categoryIds.has(node.parentId ?? ""))).toBeFalse();
  expect(firstNode?.hidden).toBe(constellation.leaves.filter((leaf) => categoryIds.has(leaf.parentId)).length);
  expect(secondNode).toBeDefined();
  expect(Math.min(...nextCategories.map((node) => node.y))).toBeGreaterThanOrEqual((firstNode?.y ?? 0) + mapMetrics.cellHeight / 2);
  expect(layout.height).toBeLessThan(expanded.height);
});

test("every group is expanded when nothing is collapsed", () => {
  expect(expanded.nodes.every((node) => node.hidden === 0)).toBeTrue();
  expect(expanded.nodes.filter((node) => node.kind === "skill")).toHaveLength(constellation.leaves.length);
});
