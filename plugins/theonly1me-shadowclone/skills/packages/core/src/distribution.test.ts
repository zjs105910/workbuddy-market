import { expect, test } from "bun:test";
import { mkdir, mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { isPackageRoot, resolveSeedDirectories, resolveSeedDirectoriesFrom } from "./distribution";

const missingMessage = "The packaged seed guidance directories are missing";

async function temporaryDirectory(): Promise<string> {
  return realpath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-root-")));
}

async function folderTree(options: {
  readonly rootDirectory: string;
  readonly manifest: Record<string, unknown>;
  readonly folders: readonly string[];
}): Promise<string> {
  await Bun.write(
    path.join(options.rootDirectory, "package.json"),
    JSON.stringify(options.manifest),
  );

  for (const folder of options.folders) {
    await mkdir(path.join(options.rootDirectory, folder), { recursive: true });
  }

  return options.rootDirectory;
}

async function packageTree(options: {
  readonly name: string;
  readonly folders: readonly string[];
}): Promise<string> {
  return folderTree({
    rootDirectory: await temporaryDirectory(),
    manifest: { name: options.name },
    folders: options.folders,
  });
}

function seedsOf(rootDirectory: string) {
  return {
    preferences: path.join(rootDirectory, "preferences"),
    skills: path.join(rootDirectory, "skills"),
  };
}

test("the package root is found by its name, without depending on any one bundled skill", async () => {
  expect(
    await isPackageRoot(
      await packageTree({ name: "@shadowclone/cli", folders: ["skills", "preferences"] }),
    ),
  ).toBeTrue();
  expect(
    await isPackageRoot(
      await packageTree({ name: "another-project", folders: ["skills", "preferences"] }),
    ),
  ).toBeFalse();
  expect(
    await isPackageRoot(await packageTree({ name: "@shadowclone/cli", folders: ["preferences"] })),
  ).toBeFalse();
});

test("an installed package keeps its seed folders next to dist", async () => {
  const installed = await packageTree({
    name: "@shadowclone/cli",
    folders: ["dist", "skills", "preferences"],
  });

  expect(await resolveSeedDirectoriesFrom(path.join(installed, "dist"))).toEqual(
    seedsOf(installed),
  );
});

test("a source checkout is found by walking up from the core package to the workspace root", async () => {
  const checkout = await folderTree({
    rootDirectory: await temporaryDirectory(),
    manifest: { name: "monorepo-root", workspaces: ["packages/*", "tooling"] },
    folders: ["packages/core/src", "skills", "preferences"],
  });

  expect(await resolveSeedDirectoriesFrom(path.join(checkout, "packages/core/src"))).toEqual(
    seedsOf(checkout),
  );
});

test("an installed package wins over the workspace that contains it", async () => {
  const checkout = await folderTree({
    rootDirectory: await temporaryDirectory(),
    manifest: { name: "monorepo-root", workspaces: ["packages/*"] },
    folders: ["skills", "preferences"],
  });
  const installed = await folderTree({
    rootDirectory: path.join(checkout, "vendor/installed"),
    manifest: { name: "@shadowclone/cli" },
    folders: ["dist", "skills", "preferences"],
  });

  expect(await resolveSeedDirectoriesFrom(path.join(installed, "dist"))).toEqual(
    seedsOf(installed),
  );
});

test("a workspace root without both seed folders, or without the packages workspace, is not a source checkout", async () => {
  const withoutPreferences = await folderTree({
    rootDirectory: await temporaryDirectory(),
    manifest: { workspaces: ["packages/*"] },
    folders: ["packages/core/src", "skills"],
  });
  const withoutPackages = await folderTree({
    rootDirectory: await temporaryDirectory(),
    manifest: { workspaces: ["apps/*"] },
    folders: ["packages/core/src", "skills", "preferences"],
  });

  await expect(
    resolveSeedDirectoriesFrom(path.join(withoutPreferences, "packages/core/src")),
  ).rejects.toThrow(missingMessage);
  await expect(
    resolveSeedDirectoriesFrom(path.join(withoutPackages, "packages/core/src")),
  ).rejects.toThrow(missingMessage);
});

test("an installed package that lost its seed folders does not borrow the workspace around node_modules", async () => {
  const workspace = await folderTree({
    rootDirectory: await temporaryDirectory(),
    manifest: { name: "someone-elses-repository", workspaces: ["packages/*"] },
    folders: ["skills", "preferences"],
  });
  const installed = await folderTree({
    rootDirectory: path.join(workspace, "node_modules/@shadowclone/cli"),
    manifest: { name: "@shadowclone/cli" },
    folders: ["dist"],
  });

  await expect(resolveSeedDirectoriesFrom(path.join(installed, "dist"))).rejects.toThrow(
    missingMessage,
  );
});

test("this checkout supplies its own skills and preferences folders", async () => {
  const checkout = path.resolve(import.meta.dir, "../../..");

  expect(await resolveSeedDirectories()).toEqual(seedsOf(checkout));
  expect(
    await Bun.file(path.join(checkout, "skills/write-plain-english/SKILL.md")).exists(),
  ).toBeTrue();
});
