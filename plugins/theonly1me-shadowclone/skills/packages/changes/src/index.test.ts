import { expect, test } from "bun:test";
import path from "node:path";
import { integrationFixture } from "@shadowclone/core/testing";
import { commitLocalChanges, listRevisions, showRevision } from "./index";

test("revision checks every destination before mutating any file", async () => {
  const { paths } = await integrationFixture();
  const first = path.join(paths.profileDirectory, "global/engineering.md");
  const second = path.join(paths.profileDirectory, "global/workflow.md");

  await expect(
    commitLocalChanges({
      paths,
      root: paths.profileDirectory,
      kind: "profile",
      updates: [
        { filePath: first, next: "new" },
        { filePath: second, next: "new", previous: "Changed elsewhere" },
      ],
    }),
  ).rejects.toThrow("subsequent edits");
  expect(await Bun.file(first).text()).toContain("Use complete names");
  expect(await listRevisions(paths)).toEqual([]);
});

test("history details redact private profile text", async () => {
  const { paths } = await integrationFixture();
  const secret = `sk-ant-${"A".repeat(90)}`;
  const filePath = path.join(paths.profileDirectory, "global/engineering.md");

  await Bun.write(filePath, `Private fixture ${secret}\n`);

  const id = await commitLocalChanges({
    paths,
    root: paths.profileDirectory,
    kind: "profile",
    updates: [{ filePath, next: "Replacement" }],
  });

  if (!id) {
    throw new Error("Expected a revision");
  }

  expect(await showRevision({ paths, id })).not.toContain(secret);
});
