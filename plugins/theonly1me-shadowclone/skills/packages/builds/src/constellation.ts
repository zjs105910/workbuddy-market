import type { BuildItem } from "./types";
import { constellationSchema, type Constellation } from "./constellationSchema";

type Source = { readonly key: string; readonly title: string; readonly order: number };

const keywordCategories: readonly (readonly [string, readonly string[]])[] = [
  ["testing", ["test", "tests", "testing", "regression", "coverage", "tdd", "e2e", "playwright"]],
  ["review", ["review", "reviews", "reviewer", "feedback", "findings", "audit"]],
  ["debugging", ["debug", "debugging", "diagnose", "bug", "bugs", "incident", "triage", "flaky"]],
  ["version-control", ["git", "merge", "rebase", "branch", "commit", "commits", "conflict", "worktree"]],
  ["pull-requests", ["pr", "prs", "pull"]],
  ["writing", ["write", "writing", "docs", "documentation", "prose", "readme", "voice"]],
  ["planning", ["plan", "planning", "architecture", "roadmap"]],
  ["typescript", ["typescript", "types", "type"]],
  ["frontend", ["ui", "css", "react", "frontend", "browser", "web", "page", "design"]],
  ["data", ["sql", "database", "data", "schema", "migration"]],
  ["delivery", ["deploy", "release", "ci", "pipeline"]],
  ["security", ["security", "secret", "secrets", "auth", "permissions"]],
  ["research", ["research", "search", "investigate", "sources"]],
];

function words(text: string): readonly string[] {
  return text.toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
}

function title(key: string): string {
  return key
    .split("-")
    .map((word) => `${word[0]?.toUpperCase() ?? ""}${word.slice(1)}`)
    .join(" ");
}

type Describable = Pick<BuildItem, "category" | "name" | "title" | "description">;

function inferredCategory(item: Describable): string {
  if (item.category) {
    return item.category;
  }

  const text = new Set(words(`${item.name} ${item.title} ${item.description}`));
  const [best] = keywordCategories
    .map(([category, keywords], index) => ({
      category,
      index,
      hits: keywords.filter((keyword) => text.has(keyword)).length,
    }))
    .filter((entry) => entry.hits > 0)
    .sort((left, right) => right.hits - left.hits || left.index - right.index);

  return best?.category ?? "more";
}

function pluginName(item: BuildItem): string {
  const parts = (item.source?.relativePath ?? "").split("/");
  const skills = parts.lastIndexOf("skills");
  const candidates = parts.slice(0, skills < 0 ? parts.length - 1 : skills).reverse();

  return (
    candidates.find((part) => part && !/^v?\d+(?:\.\d+)*$/.test(part) && part !== "latest") ??
    "plugin"
  );
}

function sourceOf(options: { readonly item: BuildItem; readonly packagedIds: ReadonlySet<string> }): Source {
  const { item } = options;

  if (item.kind === "preference") {
    return { key: "preferences", title: "Working preferences", order: 1 };
  }

  if (options.packagedIds.has(item.id)) {
    return { key: "bundled", title: "Bundled skills", order: 0 };
  }

  if (item.id.startsWith("custom:")) {
    return { key: "custom", title: "Your custom skills", order: 2 };
  }

  if (item.owner === "provider") {
    const name = pluginName(item);

    return { key: `plugin-${name}`, title: `Plugin: ${name}`, order: 4 };
  }

  return { key: "user", title: "Your skills", order: 3 };
}

function uniqueItems(items: readonly BuildItem[]): readonly { item: BuildItem; ids: string[] }[] {
  const byContent = new Map<string, { item: BuildItem; ids: string[] }>();

  for (const item of [...items].sort((left, right) => left.id.localeCompare(right.id))) {
    const key = `${item.kind}:${item.text.trim()}`;
    const existing = byContent.get(key);

    if (existing) {
      existing.ids.push(item.id);
    } else {
      byContent.set(key, { item, ids: [item.id] });
    }
  }

  return [...byContent.values()];
}

export function buildConstellation(options: {
  readonly items: readonly BuildItem[];
  readonly packagedIds: ReadonlySet<string>;
}): Constellation {
  const entries = uniqueItems(options.items).map((entry) => ({
    ...entry,
    source: sourceOf({ item: entry.item, packagedIds: options.packagedIds }),
    category: inferredCategory(entry.item),
  }));
  const sources = [...new Map(entries.map((entry) => [entry.source.key, entry.source])).values()].sort(
    (left, right) => left.order - right.order || left.title.localeCompare(right.title),
  );
  const hubs: Constellation["hubs"][number][] = [];
  const leaves: Constellation["leaves"][number][] = [];

  for (const source of sources) {
    const sourceId = `source:${source.key}`;
    const inSource = entries.filter((entry) => entry.source.key === source.key);
    const categories = [...new Set(inSource.map((entry) => entry.category))].sort((left, right) =>
      left === "more" ? 1 : right === "more" ? -1 : left.localeCompare(right),
    );

    hubs.push({ id: sourceId, title: source.title, parentId: null });

    for (const category of categories) {
      const categoryId = `category:${source.key}:${category}`;

      hubs.push({
        id: categoryId,
        title: category === "more" ? "More skills" : title(category),
        parentId: sourceId,
      });

      for (const entry of inSource
        .filter((candidate) => candidate.category === category)
        .sort((left, right) => left.item.title.localeCompare(right.item.title))) {
        leaves.push({
          id: `skill:${entry.item.id}`,
          itemIds: entry.ids,
          parentId: categoryId,
          relatedHubIds: [],
        });
      }
    }
  }

  return constellationSchema.parse({ hubs, leaves });
}

export function withCustomSkill(options: {
  readonly constellation: Constellation;
  readonly item: Describable & Pick<BuildItem, "id">;
}): Constellation {
  const sourceId = "source:custom";
  const category = inferredCategory(options.item);
  const categoryId = `category:custom:${category}`;
  const hubs = [...options.constellation.hubs];

  if (!hubs.some((hub) => hub.id === sourceId)) {
    hubs.push({ id: sourceId, title: "Your custom skills", parentId: null });
  }

  if (!hubs.some((hub) => hub.id === categoryId)) {
    hubs.push({
      id: categoryId,
      title: category === "more" ? "More skills" : title(category),
      parentId: sourceId,
    });
  }

  return {
    hubs,
    leaves: [
      ...options.constellation.leaves,
      { id: `skill:${options.item.id}`, itemIds: [options.item.id], parentId: categoryId, relatedHubIds: [] },
    ],
  };
}
