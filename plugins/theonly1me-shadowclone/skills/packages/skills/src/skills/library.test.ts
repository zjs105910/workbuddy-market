import { expect, test } from "bun:test";
import { loadSeedLibrary } from "./library";

test("the bundled library marks only write-plain-english as always on", async () => {
  const library = await loadSeedLibrary();

  expect(library.skills.filter((skill) => skill.alwaysOn).map((skill) => skill.id)).toEqual([
    "write-plain-english",
  ]);
});
