import { expect, test } from "bun:test";
import product from "@shadowclone/core/product.json";
import { publishedManifest } from "./publishedManifest";

const cliManifest = {
  name: "@shadowclone/cli",
  private: true,
  type: "module",
  description: "Sample description.",
  keywords: ["agent"],
  license: "MIT",
  repository: { type: "git", url: "git+https://example.com/sample.git" },
  homepage: "https://example.com",
  bugs: { url: "https://example.com/issues" },
  bin: { shadowclone: "bin/shadowclone.mjs" },
  exports: { ".": "./src/index.ts" },
  files: ["bin", "dist"],
  scripts: { build: "bun run scripts/build.ts" },
  devDependencies: { typescript: "~5.9" },
  dependencies: { "@shadowclone/core": "workspace:*", zod: "^4.5.4" },
};

test("the published manifest takes its name and version from product.json and drops every field outside the allowlist", () => {
  const manifest = publishedManifest({ cliManifest, product });

  expect(manifest).toEqual({
    name: product.name,
    version: product.version,
    type: "module",
    description: "Sample description.",
    keywords: ["agent"],
    license: "MIT",
    repository: { type: "git", url: "git+https://example.com/sample.git" },
    homepage: "https://example.com",
    bugs: { url: "https://example.com/issues" },
    bin: { shadowclone: "bin/shadowclone.mjs" },
    files: ["bin", "dist"],
    dependencies: { zod: "^4.5.4" },
  });
  expect(Object.keys(manifest)).not.toContain("private");
  expect(JSON.stringify(manifest)).not.toContain("workspace:");
});

test("a product version that is empty stops the stage with a message that names product.json", () => {
  expect(() =>
    publishedManifest({ cliManifest, product: { name: "@shadowclone/cli", version: "" } }),
  ).toThrow("product.json is not valid:\nversion: product.json needs a version");
});
