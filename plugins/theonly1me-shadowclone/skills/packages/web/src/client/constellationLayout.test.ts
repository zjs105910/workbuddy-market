import { expect, test } from "bun:test";
import { buildConstellation } from "@shadowclone/builds/browser";
import { syntheticLibrary } from "./constellationFixtures";
import { layoutConstellation, mapMetrics, type PositionedConstellationNode } from "./constellationLayout";

type Box = { readonly id: string; readonly left: number; readonly right: number; readonly top: number; readonly bottom: number };

function boxes(node: PositionedConstellationNode): readonly Box[] {
  const radius = node.kind === "skill" ? 26 : node.kind === "root" ? 26 : 23;
  const labelTop = node.kind === "skill" ? 22 : 32;

  return [
    { id: `${node.id}:mark`, left: node.x - radius, right: node.x + radius, top: node.y - radius, bottom: node.y + radius },
    {
      id: `${node.id}:label`,
      left: node.x - mapMetrics.labelWidth / 2,
      right: node.x + mapMetrics.labelWidth / 2,
      top: node.y + labelTop,
      bottom: node.y + labelTop + 34,
    },
  ];
}

function overlapping(options: { readonly nodes: readonly PositionedConstellationNode[] }): readonly string[] {
  const all = options.nodes.flatMap((node) => boxes(node).map((box) => ({ box, node: node.id })));
  const overlaps: string[] = [];

  for (const [index, left] of all.entries()) {
    for (const right of all.slice(index + 1)) {
      if (left.node === right.node) continue;

      if (
        left.box.left < right.box.right &&
        right.box.left < left.box.right &&
        left.box.top < right.box.bottom &&
        right.box.top < left.box.bottom
      ) {
        overlaps.push(`${left.box.id} ${right.box.id}`);
      }
    }
  }

  return overlaps;
}

for (const count of [20, 70, 500]) {
  for (const width of [720, 1180, 1600]) {
    test(`shows all ${count} skills at ${width} px without overlap, zoom, or a hub per filler word`, () => {
      const library = syntheticLibrary({ count });
      const constellation = buildConstellation(library);
      const layout = layoutConstellation({ constellation, width });
      const skills = layout.nodes.filter((node) => node.kind === "skill");

      expect(skills).toHaveLength(constellation.leaves.length);
      expect(new Set(skills.map((node) => node.id)).size).toBe(skills.length);
      expect(overlapping({ nodes: layout.nodes })).toEqual([]);
      expect(
        layout.nodes.every(
          (node) =>
            node.x - mapMetrics.labelWidth / 2 >= 0 &&
            node.x + mapMetrics.labelWidth / 2 <= width &&
            node.y - 26 >= 0 &&
            node.y + 66 <= layout.height,
        ),
      ).toBeTrue();
      expect(
        layout.nodes.filter((node) => node.kind === "category").map((node) => node.title),
      ).not.toContainEqual(expect.stringMatching(/^(And|The|Of|To|With|For)\b|\s\d+$/));
      expect(new Set(skills.map((node) => layout.links.some((link) => link.targetX === node.x && link.targetY === node.y))))
        .toEqual(new Set([true]));
    });
  }
}

test("small categories share a row and a large category wraps inside its own block", () => {
  const library = syntheticLibrary({ count: 70 });
  const layout = layoutConstellation({ constellation: buildConstellation(library), width: 1180 });
  const categories = layout.nodes.filter((node) => node.kind === "category");
  const rows = new Set(categories.map((node) => node.y));

  expect(rows.size).toBeLessThan(categories.length);
  expect(layout.links.filter((link) => link.sibling)).toHaveLength(categories.length - rows.size);
  expect(
    layout.nodes
      .filter((node) => node.kind === "skill")
      .every((node) => {
        const category = categories.find((candidate) => candidate.id === node.parentId);

        return category !== undefined && node.x > category.x && node.y >= category.y - mapMetrics.jitterY;
      }),
  ).toBeTrue();
});

test("a wider map fits more skills on each line and needs less height", () => {
  const constellation = buildConstellation(syntheticLibrary({ count: 70 }));
  const narrow = layoutConstellation({ constellation, width: 900 });
  const wide = layoutConstellation({ constellation, width: 1600 });

  expect(wide.height).toBeLessThan(narrow.height);
});
