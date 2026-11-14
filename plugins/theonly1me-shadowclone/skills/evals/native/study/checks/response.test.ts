import { expect, test } from "bun:test";
import { extractReply, sentences } from "./response";

test("a labeled review reply excludes the surrounding assistant note", () => {
  const response = "Suggested reply:\nThe limit is validated in paginate.\n\nI can also add a test.";

  expect(extractReply(response)).toBe("The limit is validated in paginate.");
});

test("common abbreviations stay inside one sentence", () => {
  expect(sentences("Use a concise phrase, e.g. a noun. Keep it direct.")).toEqual([
    "Use a concise phrase, e.g. a noun.",
    "Keep it direct.",
  ]);
  expect(sentences("The reply is brief, i.e. one sentence.")).toHaveLength(1);
});
