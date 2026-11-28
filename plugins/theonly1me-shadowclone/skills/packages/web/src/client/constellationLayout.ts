import type { Constellation } from "@shadowclone/builds/browser";

export type PositionedConstellationNode = {
  readonly id: string;
  readonly title: string;
  readonly itemIds: readonly string[];
  readonly kind: "root" | "source" | "category" | "skill";
  readonly parentId: string | null;
  readonly x: number;
  readonly y: number;
  readonly hidden: number;
};

export type PositionedConstellationLink = {
  readonly id: string;
  readonly sourceX: number;
  readonly sourceY: number;
  readonly targetX: number;
  readonly targetY: number;
  readonly sibling: boolean;
};

export const mapMetrics = {
  padding: 32,
  rootX: 56,
  sourceX: 176,
  categoryX: 296,
  cellWidth: 120,
  cellHeight: 96,
  groupGap: 12,
  sourceGap: 28,
  labelWidth: 108,
  jitterX: 4,
  jitterY: 5,
} as const;

function jitter(options: { readonly key: string; readonly range: number }): number {
  let hash = 2166136261;

  for (const character of options.key) {
    hash = Math.imul(hash ^ (character.codePointAt(0) ?? 0), 16777619);
  }

  return ((hash >>> 0) / 4294967295) * options.range * 2 - options.range;
}

export function cellsPerRow(width: number): number {
  const available = width - mapMetrics.categoryX - mapMetrics.padding + mapMetrics.cellWidth / 2;

  return Math.max(2, Math.floor(available / mapMetrics.cellWidth));
}

function link(options: {
  readonly from: PositionedConstellationNode;
  readonly to: PositionedConstellationNode;
  readonly sibling?: boolean;
}): PositionedConstellationLink {
  return {
    id: `${options.from.id}:${options.to.id}`,
    sourceX: options.from.x,
    sourceY: options.from.y,
    targetX: options.to.x,
    targetY: options.to.y,
    sibling: options.sibling ?? false,
  };
}

type Block = {
  readonly category: Constellation["hubs"][number];
  readonly members: readonly Constellation["leaves"][number][];
  readonly hidden: number;
  readonly columns: number;
};

function packRows(options: { readonly blocks: readonly Block[]; readonly cells: number }): readonly (readonly Block[])[] {
  const rows: Block[][] = [];
  let used = options.cells;

  for (const block of options.blocks) {
    if (used + 1 + block.columns > options.cells) {
      rows.push([]);
      used = 0;
    }

    rows.at(-1)?.push(block);
    used += 1 + block.columns;
  }

  return rows;
}

export function layoutConstellation(options: {
  readonly constellation: Constellation;
  readonly width: number;
  readonly collapsed?: ReadonlySet<string>;
}): {
  readonly nodes: readonly PositionedConstellationNode[];
  readonly links: readonly PositionedConstellationLink[];
  readonly height: number;
} {
  const cells = cellsPerRow(options.width);
  const { hubs, leaves } = options.constellation;
  const nodes: PositionedConstellationNode[] = [];
  const links: PositionedConstellationLink[] = [];
  const sourceNodes: PositionedConstellationNode[] = [];
  const collapsed = options.collapsed ?? new Set<string>();
  let cursor = mapMetrics.padding;

  for (const source of hubs.filter((hub) => hub.parentId === null)) {
    const categoryNodes: PositionedConstellationNode[] = [];
    const rowStarts: PositionedConstellationNode[] = [];
    const categories = hubs.filter((hub) => hub.parentId === source.id);
    const sourceCollapsed = collapsed.has(source.id);
    const blocks = (sourceCollapsed ? [] : categories).map((category) => {
      const all = leaves.filter((leaf) => leaf.parentId === category.id);
      const members = collapsed.has(category.id) ? [] : all;

      return {
        category,
        members,
        hidden: all.length - members.length,
        columns: Math.max(1, Math.min(members.length, cells - 1)),
      };
    });

    for (const row of packRows({ blocks, cells })) {
      let cell = 0;
      let lines = 1;
      let previousHub: PositionedConstellationNode | null = null;

      for (const block of row) {
        const x = mapMetrics.categoryX + cell * mapMetrics.cellWidth;
        const categoryNode: PositionedConstellationNode = {
          id: block.category.id,
          title: block.category.title,
          itemIds: [],
          kind: "category",
          parentId: source.id,
          x,
          y: cursor + mapMetrics.cellHeight / 2,
          hidden: block.hidden,
        };
        let previous = categoryNode;

        categoryNodes.push(categoryNode);

        if (previousHub) links.push(link({ from: previousHub, to: categoryNode, sibling: true }));
        else rowStarts.push(categoryNode);

        for (const [index, leaf] of block.members.entries()) {
          const column = index % block.columns;
          const node: PositionedConstellationNode = {
            id: leaf.id,
            title: "",
            itemIds: leaf.itemIds,
            kind: "skill",
            parentId: block.category.id,
            hidden: 0,
            x: x + (column + 1) * mapMetrics.cellWidth + jitter({ key: leaf.id, range: mapMetrics.jitterX }),
            y:
              cursor +
              Math.floor(index / block.columns) * mapMetrics.cellHeight +
              mapMetrics.cellHeight / 2 +
              jitter({ key: `${leaf.id}:y`, range: mapMetrics.jitterY }),
          };

          links.push(link({ from: column === 0 ? categoryNode : previous, to: node }));
          nodes.push(node);
          previous = node;
        }

        lines = Math.max(lines, Math.ceil(block.members.length / block.columns));
        cell += 1 + block.columns;
        previousHub = categoryNode;
      }

      cursor += lines * mapMetrics.cellHeight + mapMetrics.groupGap;
    }

    const first = categoryNodes[0];
    const last = categoryNodes.at(-1);
    const sourceNode: PositionedConstellationNode = {
      id: source.id,
      title: source.title,
      itemIds: [],
      kind: "source",
      parentId: "constellation-root",
      x: mapMetrics.sourceX,
      y: first && last ? (first.y + last.y) / 2 : cursor + mapMetrics.cellHeight / 2,
      hidden: sourceCollapsed ? leaves.filter((leaf) => categories.some((category) => category.id === leaf.parentId)).length : 0,
    };

    if (sourceCollapsed) cursor += mapMetrics.cellHeight;

    sourceNodes.push(sourceNode);
    nodes.push(sourceNode, ...categoryNodes);
    links.push(...rowStarts.map((node) => link({ from: sourceNode, to: node })));
    cursor += mapMetrics.sourceGap;
  }

  const firstSource = sourceNodes[0];
  const lastSource = sourceNodes.at(-1);
  const root: PositionedConstellationNode = {
    id: "constellation-root",
    title: "Shadowclone",
    itemIds: [],
    kind: "root",
    parentId: null,
    hidden: 0,
    x: mapMetrics.rootX,
    y:
      firstSource && lastSource
        ? (firstSource.y + lastSource.y) / 2
        : mapMetrics.padding + mapMetrics.cellHeight / 2,
  };

  links.push(...sourceNodes.map((node) => link({ from: root, to: node })));

  return {
    nodes: [root, ...nodes],
    links,
    height: Math.max(cursor + mapMetrics.padding, mapMetrics.cellHeight * 2),
  };
}
