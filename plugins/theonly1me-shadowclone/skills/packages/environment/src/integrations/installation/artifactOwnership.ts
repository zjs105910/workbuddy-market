import path from "node:path";
import { readBoundedFile, maximumProfileBytes, ownedWrite } from "@shadowclone/core";
import { artifactRelativePaths } from "./installPaths";
import { resolveArtifactPath } from "./installTarget";
import type { Installation, InstalledArtifact } from "./installState";

export function artifactFingerprint(content: string): string {
  return new Bun.CryptoHasher("sha256").update(content).digest("hex");
}

export async function artifactIsOwned(options: {
  readonly directory: string;
  readonly artifact: InstalledArtifact;
  readonly installation?: Installation | null;
}): Promise<boolean> {
  const expected = options.installation?.fingerprints?.[options.artifact];

  if (!expected) {
    return false;
  }

  const content = await readBoundedFile({
    filePath: path.join(
      options.directory,
      artifactRelativePaths[options.artifact],
    ),
    roots: [options.directory],
    maximumBytes: maximumProfileBytes,
  });

  return content !== null && artifactFingerprint(content) === expected;
}

export async function checkArtifactWrite(options: {
  readonly directory: string;
  readonly artifact: InstalledArtifact;
  readonly installation: Installation | null;
}): Promise<string> {
  const target = await resolveArtifactPath({
    root: options.directory,
    relativePath: artifactRelativePaths[options.artifact],
  });

  if (target === null) {
    throw new Error("Installation target contains an unsafe path");
  }

  if ((await Bun.file(target).exists()) && !(await artifactIsOwned(options))) {
    throw new Error(
      "Existing agent or skill was not installed by this version or has user edits; preserve it before reinstalling",
    );
  }

  return target;
}

export async function writeInstalledArtifact(options: {
  readonly target: string;
  readonly content: string;
}): Promise<string> {
  await ownedWrite({ path: options.target, content: options.content });

  return artifactFingerprint(options.content);
}
