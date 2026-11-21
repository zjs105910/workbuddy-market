import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { findVersionMismatches, readReleaseVersions } from "./releaseVersions";

async function treeWith(files: Record<string, unknown>): Promise<string> {
  const rootDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-release-versions-"),
  );

  for (const [file, content] of Object.entries(files)) {
    await Bun.write(
      path.join(rootDirectory, file),
      JSON.stringify(content),
    );
  }

  return rootDirectory;
}

function releaseConfig(paths: readonly string[]) {
  return {
    packages: {
      ".": {
        "extra-files": paths.map((file) => ({
          type: "json",
          path: file,
          jsonpath: "$.version",
        })),
      },
    },
  };
}

test("the product identity and every manifest that Release Please bumps agree with package.json", async () => {
  const versions = await readReleaseVersions({
    rootDirectory: path.resolve(import.meta.dir, "../.."),
  });

  expect(findVersionMismatches(versions)).toEqual([]);
  expect(versions.product).not.toBeNull();
  expect(versions.bumped.length).toBeGreaterThan(1);
});

test("a product version that differs from package.json is reported", async () => {
  const rootDirectory = await treeWith({
    "package.json": { name: "shadowclone", version: "1.2.3" },
    "packages/cli/package.json": { name: "@shadowclone/cli" },
    "packages/core/src/product.json": { name: "@shadowclone/cli", version: "1.2.2" },
    ".github/release-please-config.json": releaseConfig(["packages/core/src/product.json"]),
  });

  expect(
    findVersionMismatches(await readReleaseVersions({ rootDirectory })),
  ).toEqual([
    "packages/core/src/product.json has version 1.2.2, but package.json has 1.2.3",
  ]);
});

test("a plugin manifest version and a product name that differ are both reported", async () => {
  const rootDirectory = await treeWith({
    "package.json": { name: "shadowclone", version: "1.2.3" },
    "packages/cli/package.json": { name: "@shadowclone/cli" },
    "packages/core/src/product.json": { name: "shadowclone", version: "1.2.3" },
    "plugins/plugin.json": { name: "plugin", version: "1.2.0" },
    ".github/release-please-config.json": releaseConfig([
      "packages/core/src/product.json",
      "plugins/plugin.json",
    ]),
  });

  expect(
    findVersionMismatches(await readReleaseVersions({ rootDirectory })),
  ).toEqual([
    "plugins/plugin.json has version 1.2.0, but package.json has 1.2.3",
    "packages/core/src/product.json has name shadowclone, but packages/cli/package.json has @shadowclone/cli",
  ]);
});

test("a product file that Release Please does not bump is reported", async () => {
  const rootDirectory = await treeWith({
    "package.json": { name: "shadowclone", version: "1.2.3" },
    "packages/cli/package.json": { name: "@shadowclone/cli" },
    ".github/release-please-config.json": releaseConfig([]),
  });

  expect(
    findVersionMismatches(await readReleaseVersions({ rootDirectory })),
  ).toEqual(["product.json is not listed in the Release Please extra-files"]);
});
