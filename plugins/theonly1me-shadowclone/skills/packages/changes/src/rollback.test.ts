import { expect, test } from "bun:test";
import path from "node:path";
import { integrationFixture } from "@shadowclone/core/testing";
import { replaceLocalText } from "@shadowclone/core";
import { applyRevisionFiles } from "./apply";

test("a later write failure rolls back the files already changed", async () => {
  const { paths } = await integrationFixture();
  const filePath = path.join(paths.profileDirectory, "global/engineering.md");
  const before = await Bun.file(filePath).text();
  let writes = 0;

  await expect(
    applyRevisionFiles({
      revision: {
        id: crypto.randomUUID(),
        root: paths.profileDirectory,
        kind: "profile",
        status: "prepared",
        createdAt: Date.now(),
        changes: [
          { relativePath: "global/engineering.md", before, after: "Changed" },
          {
            relativePath: "global/workflow.md",
            before: null,
            after: "New guidance",
          },
        ],
      },
      replace: async (change) => {
        writes += 1;

        if (writes === 2) {
          throw new Error("Fixture disk failure");
        }

        await replaceLocalText(change);
      },
    }),
  ).rejects.toThrow("Fixture disk failure");
  expect(writes).toBe(2);
  expect(await Bun.file(filePath).text()).toBe(before);
});
