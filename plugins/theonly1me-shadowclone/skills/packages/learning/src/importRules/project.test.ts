import { expect, test } from "bun:test";
import { mkdtemp, rename } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { compileProfile, readGeneratedProfileState } from "@shadowclone/profile";
import { normalizeRemoteRepository } from "@shadowclone/sessions";
import { maximumGuidanceBytes } from "./discovery";
import { importRepositoryGuidance } from "./importRepositoryGuidance";

async function temporaryDirectory(prefix: string): Promise<string> {
  return mkdtemp(path.join(os.tmpdir(), prefix));
}

test("reuses one imported key across checkouts of the same remote", async () => {
  const home = await temporaryDirectory("shadowclone-project-home-");
  const firstCheckout = await temporaryDirectory("shadowclone-checkout-one-");
  const secondCheckout = await temporaryDirectory("shadowclone-checkout-two-");
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const remote = "git@github.com:acme/platform.git";

  await Bun.write(
    path.join(firstCheckout, "AGENTS.md"),
    "Use the first wording.",
  );
  await Bun.write(
    path.join(secondCheckout, "AGENTS.md"),
    "Use the second wording.",
  );

  await importRepositoryGuidance({
    paths,
    workingDirectory: firstCheckout,
    gitMetadataEnabled: true,
    readRemote: async () => remote,
  });

  const [first] = await readGeneratedProfileState(paths.profileManifestFile);

  await importRepositoryGuidance({
    paths,
    workingDirectory: secondCheckout,
    gitMetadataEnabled: true,
    readRemote: async () => remote,
  });

  const [second] = await readGeneratedProfileState(paths.profileManifestFile);

  expect(second?.key).toBe(first?.key);
  expect(second?.importReference?.repositoryAliases).toHaveLength(3);
});

test("compiles only the exact project profile for one origin", async () => {
  const home = await temporaryDirectory("shadowclone-project-home-");
  const firstRepository = await temporaryDirectory("shadowclone-project-one-");
  const secondRepository = await temporaryDirectory("shadowclone-project-two-");
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const firstRemote = "git@github.com:acme/platform.git";
  const secondRemote = "git@github.com:acme/console.git";

  await Bun.write(
    path.join(firstRepository, "AGENTS.md"),
    "Platform guidance.",
  );
  await Bun.write(
    path.join(secondRepository, "AGENTS.md"),
    "Console guidance.",
  );
  await importRepositoryGuidance({
    paths,
    workingDirectory: firstRepository,
    gitMetadataEnabled: true,
    readRemote: async () => firstRemote,
  });
  await importRepositoryGuidance({
    paths,
    workingDirectory: secondRepository,
    gitMetadataEnabled: true,
    readRemote: async () => secondRemote,
  });

  const repository = normalizeRemoteRepository(firstRemote);

  if (!repository) {
    throw new Error("Expected a normalized test repository");
  }

  const compilation = await compileProfile({
    input: {
      kind: "directory",
      profileDirectory: paths.profileDirectory,
      origin: repository.origin,
      targetRepo: repository.profileFileName,
    },
    repositoryContext: "missing",
  });

  expect(compilation.markdown).toContain("Platform guidance.");
  expect(compilation.markdown).not.toContain("Console guidance.");
});

test("treats a renamed source as a new imported identity", async () => {
  const home = await temporaryDirectory("shadowclone-project-home-");
  const repository = await temporaryDirectory("shadowclone-project-source-");
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const original = path.join(repository, "CLAUDE.md");

  await Bun.write(original, "Keep the same content.");
  await importRepositoryGuidance({
    paths,
    workingDirectory: repository,
    gitMetadataEnabled: false,
  });

  const [first] = await readGeneratedProfileState(paths.profileManifestFile);

  await rename(original, path.join(repository, "AGENTS.md"));

  await importRepositoryGuidance({
    paths,
    workingDirectory: repository,
    gitMetadataEnabled: false,
  });

  const state = await readGeneratedProfileState(paths.profileManifestFile);
  const present = state.find((entry) => entry.disposition === "present");
  const retired = state.find((entry) => entry.disposition === "retired");

  expect(present?.key).not.toBe(first?.key);
  expect(retired?.key).toBe(first?.key);
});

test("fails batch validation before creating profile state", async () => {
  const home = await temporaryDirectory("shadowclone-project-home-");
  const repository = await temporaryDirectory("shadowclone-project-large-");
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });

  await Bun.write(
    path.join(repository, "CLAUDE.md"),
    "x".repeat(maximumGuidanceBytes + 1),
  );

  await expect(
    importRepositoryGuidance({
      paths,
      workingDirectory: repository,
      gitMetadataEnabled: false,
    }),
  ).rejects.toThrow("Repository guidance exceeds the supported byte limit");

  expect(await Bun.file(paths.profileManifestFile).exists()).toBeFalse();
});
