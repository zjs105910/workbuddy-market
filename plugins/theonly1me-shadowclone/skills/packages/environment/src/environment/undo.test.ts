import { expect, test } from "bun:test";
import path from "node:path";
import { commitLocalChanges, listRevisions } from "@shadowclone/changes";
import { integrationFixture } from "@shadowclone/core/testing";
import { undoRevision } from "./undo";

test("revision history restores exact prior content and preserves later manual changes", async () => {
  const { paths } = await integrationFixture();
  const filePath = path.join(paths.profileDirectory, "global/engineering.md");
  const previous = await Bun.file(filePath).text();
  const id = await commitLocalChanges({
    paths,
    root: paths.profileDirectory,
    kind: "profile",
    updates: [{ filePath, next: "Learned preference\n", previous }],
  });

  if (!id) {
    throw new Error("Expected a revision");
  }

  expect(await listRevisions(paths)).toHaveLength(1);

  await undoRevision({ paths, id });

  expect(await Bun.file(filePath).text()).toBe(previous);

  await Bun.write(filePath, "My manual change\n");

  await expect(undoRevision({ paths, id })).rejects.toThrow("subsequent edits");
  expect(await Bun.file(filePath).text()).toBe("My manual change\n");
});
