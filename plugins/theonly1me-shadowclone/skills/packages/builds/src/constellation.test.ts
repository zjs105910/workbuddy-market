import { describe, expect, test } from "bun:test";
import { buildConstellation, withCustomSkill } from "./constellation";
import type { BuildItem } from "./types";

function item(options: {
  readonly id: string;
  readonly category?: string | null;
  readonly text?: string;
  readonly name?: string;
  readonly description?: string;
  readonly owner?: BuildItem["owner"];
  readonly kind?: BuildItem["kind"];
  readonly pluginPath?: string;
}): BuildItem {
  const name = options.name ?? options.id;

  return {
    id: options.id,
    name,
    title: name.replaceAll("-", " "),
    description: options.description ?? `Guidance for ${name}`,
    text: options.text ?? `Instructions for ${options.id}`,
    kind: options.kind ?? "skill",
    category: options.category ?? null,
    section: "workflow",
    axis: null,
    alwaysOn: false,
    owner: options.owner ?? "user",
    ...(options.pluginPath
      ? {
          source: {
            id: options.id,
            root: {
              id: "0".repeat(64),
              directory: "/plugins",
              cwd: "/",
              scope: "global",
              owner: "third-party",
              destination: "/plugins",
              enabled: true,
            },
            relativePath: options.pluginPath,
            raw: "",
            redacted: "",
            fingerprint: "",
            name,
            description: "",
            body: "",
          },
        }
      : {}),
  };
}

function titles(options: { readonly items: readonly BuildItem[]; readonly packagedIds?: readonly string[] }) {
  const constellation = buildConstellation({
    items: options.items,
    packagedIds: new Set(options.packagedIds ?? []),
  });

  return constellation.hubs.map((hub) => `${hub.parentId === null ? "" : "  "}${hub.title}`);
}

describe("buildConstellation", () => {
  test("groups skills by source first and category second", () => {
    expect(
      titles({
        items: [
          item({ id: "tests-that-catch-bugs", category: "testing" }),
          item({ id: "my-review", category: "review" }),
          item({ id: "typed-changes", owner: "provider", pluginPath: "publisher/typescript-kit/1.0/skills/typed-changes/SKILL.md" }),
          item({ id: "prefer-small-diffs", kind: "preference" }),
          item({ id: "custom:release-notes", category: "delivery" }),
        ],
        packagedIds: ["tests-that-catch-bugs"],
      }),
    ).toEqual([
      "Bundled skills",
      "  Testing",
      "Working preferences",
      "  More skills",
      "Your custom skills",
      "  Delivery",
      "Your skills",
      "  Review",
      "Plugin: typescript-kit",
      "  More skills",
    ]);
  });

  test("infers a category from known keywords and never makes a hub from a filler word", () => {
    const hubTitles = titles({
      items: [
        item({ id: "and-then-more", description: "And then the rest of it" }),
        item({ id: "flaky-hunter", description: "Find a flaky test and fix the bug" }),
        item({ id: "rebase-helper", description: "Rebase a branch onto main" }),
      ],
    });

    expect(hubTitles).toEqual(["Your skills", "  Debugging", "  Version Control", "  More skills"]);
  });

  test("keeps every skill of a large library in one hub per category", () => {
    const constellation = buildConstellation({
      items: Array.from({ length: 500 }, (_, index) => item({ id: `skill-${index}`, category: `topic-${index % 7}` })),
      packagedIds: new Set(),
    });

    expect(constellation.leaves).toHaveLength(500);
    expect(constellation.hubs.filter((hub) => hub.parentId !== null)).toHaveLength(7);
    expect(constellation.hubs.some((hub) => /\d$/.test(hub.title) && !hub.title.startsWith("Topic"))).toBeFalse();
  });

  test("collapses exact content and keeps divergent namesakes", () => {
    const constellation = buildConstellation({
      items: [
        item({ id: "first", name: "review", text: "same" }),
        item({ id: "copy", name: "review-copy", text: "same" }),
        item({ id: "variant", name: "review", text: "different" }),
      ],
      packagedIds: new Set(),
    });

    expect(constellation.leaves).toHaveLength(2);
    expect(constellation.leaves.find((leaf) => leaf.itemIds.length === 2)?.itemIds).toEqual(["copy", "first"]);
  });

  test("adds a new custom skill under its own source", () => {
    const constellation = withCustomSkill({
      constellation: buildConstellation({ items: [item({ id: "my-review", category: "review" })], packagedIds: new Set() }),
      item: { id: "custom:abc", name: "deploy-notes", title: "Deploy notes", description: "Write release notes", category: null },
    });

    expect(constellation.hubs.map((hub) => hub.id)).toEqual([
      "source:user",
      "category:user:review",
      "source:custom",
      "category:custom:delivery",
    ]);
    expect(constellation.leaves.at(-1)).toEqual({
      id: "skill:custom:abc",
      itemIds: ["custom:abc"],
      parentId: "category:custom:delivery",
      relatedHubIds: [],
    });
  });
});
