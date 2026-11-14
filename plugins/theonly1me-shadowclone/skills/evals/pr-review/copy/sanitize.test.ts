import { expect, test } from "bun:test";
import { sanitizeBody } from "./sanitize";

test("a copied description cannot notify or backlink the source repository", () => {
  const body = "Fixes #123 and vitejs/vite#45, see https://github.com/vitejs/vite/pull/67. Thanks @someone <!-- template -->";

  expect(sanitizeBody(body)).toBe("Fixes upstream issue 123 and (upstream reference removed), see (upstream link removed). Thanks someone");
});

test("a nested HTML comment cannot leave an opening marker that hides the rest of the description", () => {
  const sanitized = sanitizeBody("Keep this. <!<!--- -->-- hidden? Still here.");

  expect(sanitized).not.toContain("<!--");
  expect(sanitized).toEndWith("Still here.");
});
