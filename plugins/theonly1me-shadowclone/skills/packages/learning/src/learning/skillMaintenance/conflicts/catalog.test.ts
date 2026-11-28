import { expect, test } from "bun:test";
import type { DiscoveredSkill } from "@shadowclone/skills";
import { libraryCatalogBatches, resolveCatalogPair, shareSkillScope } from "./catalog";

function skill(options: { readonly name: string; readonly repository?: string }): DiscoveredSkill {
  const directory = options.repository ?? "/private/tmp/synthetic-catalog";
  return {
    id: options.name,
    name: options.name,
    description: "Prepare release notes".repeat(40),
    fingerprint: options.name,
    raw: "", redacted: "", body: "", relativePath: `${options.name}/SKILL.md`,
    root: {
      id: options.name, directory, cwd: directory, destination: directory,
      scope: options.repository ? "repository" : "global", owner: "user", enabled: true,
    },
  };
}

test("catalog work includes overlapping skills beyond a single batch", () => {
  const skills = Array.from({ length: 40 }, (_, index) => skill({ name: `release-${index}` }));
  const batches = libraryCatalogBatches(skills);
  const [first] = skills;
  const last = skills.at(-1);
  if (!first || !last) throw new Error("Expected synthetic skills");

  const batch = batches.find((entry) => entry.left.includes(first) && entry.right.includes(last));
  if (!batch) throw new Error("Expected a comparison across batches");

  expect(batches.length).toBeGreaterThan(1);
  expect(resolveCatalogPair({ batch, left: first.id, right: last.id }).map(({ id }) => id))
    .toEqual([first.id, last.id]);
  expect(batches.every(({ left, right }) => left.length <= 32 && right.length <= 32)).toBeTrue();
});

test("global skills can overlap with a repository but unrelated repositories cannot", () => {
  const global = skill({ name: "global-release" });
  const first = skill({ name: "first-release", repository: "/private/tmp/synthetic-first" });
  const second = skill({ name: "second-release", repository: "/private/tmp/synthetic-second" });

  expect(shareSkillScope([global, first])).toBeTrue();
  expect(shareSkillScope([first, second])).toBeFalse();
  expect(libraryCatalogBatches([first, second])).toEqual([]);
  expect(() => resolveCatalogPair({
    batch: { fingerprint: "synthetic", left: [first], right: [second] },
    left: first.id, right: second.id,
  })).toThrow("unrelated");
});
