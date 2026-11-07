import { expect, test } from "bun:test";
import { assertNotCoveredRouting } from "./skillRouting";

test("skill routing cannot be discarded as a duplicate skill body", () => {
  const body = "Load clean-code before editing, and add scoped-fix for fixes.";

  expect(() =>
    assertNotCoveredRouting({ body, reason: "skill-covered" }),
  ).toThrow("routing");
  expect(() =>
    assertNotCoveredRouting({
      body: "Use complete names.",
      reason: "skill-covered",
    }),
  ).not.toThrow();
  expect(() =>
    assertNotCoveredRouting({ body, reason: "user-rejected" }),
  ).not.toThrow();
});
