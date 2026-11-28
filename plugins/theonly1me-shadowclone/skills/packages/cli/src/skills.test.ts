import { expect, test } from "bun:test";
import { resolveSeedDirectories } from "@shadowclone/core";
import { loadSeedLibrary } from "@shadowclone/skills";
import { renderSeedLibrary } from "./skills";

test("lists every preference and Agent Skill exactly once", async () => {
  const seeds = await resolveSeedDirectories();
  const library = await loadSeedLibrary({
    preferencesDirectory: seeds.preferences,
    skillsDirectory: seeds.skills,
  });
  const lines = renderSeedLibrary(library);

  expect(lines[0]).toBe("Profile preference axes");
  expect(lines).toContain("Skill axes");
  expect(lines).toContain("Optional skills");
  expect(lines).toContain("Always on skills");

  for (const entry of library.guidance) {
    expect(
      lines.filter((line) => line.endsWith(`${entry.id}: ${entry.title}`)),
    ).toHaveLength(1);
  }
});

test("lists write-plain-english as always on and not as optional", async () => {
  const lines = renderSeedLibrary(await loadSeedLibrary());
  const optionalStart = lines.indexOf("Optional skills");
  const alwaysOnStart = lines.indexOf("Always on skills");
  const entry = "  write-plain-english: Write Plain English";

  expect(lines.slice(optionalStart, alwaysOnStart)).not.toContain(entry);
  expect(lines.slice(alwaysOnStart)).toEqual(["Always on skills", entry]);
});
