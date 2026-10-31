import { expect, test } from "bun:test";
import { parseRecallOptions } from "./recall";

test("recall accepts a phrase and a bounded result limit", () => {
  expect(parseRecallOptions(["queue", "retry", "--limit", "5"])).toEqual({
    query: "queue retry",
    limit: 5,
  });
  expect(parseRecallOptions(["queue", "--limit", "0"])).toBeNull();
  expect(parseRecallOptions(["queue", "--limit", "11"])).toBeNull();
  expect(parseRecallOptions(["--unknown"])).toBeNull();
});
