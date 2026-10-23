import { expect, test } from "bun:test";
import { learn } from "@shadowclone/cli";

test("programmatic limits cannot bypass the declared call ceiling or non-deep mode", async () => {
  await expect(
    learn({
      deep: true,
      maximumCalls: 16,
      limits: { maximumCalls: 17, timeoutMilliseconds: 1200000, maximumCostUsd: 1.6 },
    }),
  ).rejects.toThrow("matching call ceiling");
  await expect(
    learn({
      deep: false,
      maximumCalls: 16,
      limits: { maximumCalls: 16, timeoutMilliseconds: 1200000, maximumCostUsd: 1.6 },
    }),
  ).rejects.toThrow("require deep learning");
});
