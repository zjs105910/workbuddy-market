import { expect, test } from "bun:test";
import { mapWithConcurrency } from "./concurrency";

test("preserves input order when work completes out of order", async () => {
  let active = 0;
  let peakActive = 0;
  const completionOrder: number[] = [];

  const result = await mapWithConcurrency({
    items: [0, 1, 2, 3],
    limit: 2,
    run: async (item) => {
      active += 1;
      peakActive = Math.max(peakActive, active);
      await new Promise<void>((resolve) => {
        setTimeout(resolve, item === 0 ? 30 : 1);
      });
      completionOrder.push(item);
      active -= 1;

      return item * 2;
    },
  });

  expect(peakActive).toBe(2);
  expect(completionOrder[0]).not.toBe(0);
  expect(result).toEqual([0, 2, 4, 6]);
});

test("rejects the entire mapping when an item rejects", async () => {
  await expect(
    mapWithConcurrency({
      items: [1, 2, 3],
      limit: 2,
      run: async (item) => {
        if (item === 2) {
          throw new Error("failed item");
        }

        return item;
      },
    }),
  ).rejects.toThrow("failed item");
});

test("finishes when the limit exceeds the item count", async () => {
  const result = await mapWithConcurrency({
    items: [1, 2],
    limit: 8,
    run: async (item) => item * 2,
  });

  expect(result).toEqual([2, 4]);
});
