import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { originDirectoryName } from "@shadowclone/sessions";
import type { ProfileRule } from "./profile";

export const legacy = "github.com--acme";

export const canonical = originDirectoryName("github.com/acme");

export function rule(options: {
  readonly key: string;
  readonly title: string;
  readonly originDirectory: string;
}): ProfileRule {
  return {
    key: options.key,
    title: options.title,
    body: `Apply ${options.title}.`,
    section: "engineering",
    scope: "org",
    originDirectory: options.originDirectory,
    repositoryName: null,
    source: "mined",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 1,
    lastSeen: "2026-09-18",
    sessions: 1,
    origins: ["github.com/acme"],
    importReference: null,
  };
}

export async function fixture() {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-repair-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });

  const source = path.join(
    paths.profileDirectory,
    "org",
    legacy,
    "engineering.md",
  );

  const target = path.join(
    paths.profileDirectory,
    "org",
    canonical,
    "engineering.md",
  );

  await mkdir(path.dirname(source), { recursive: true });
  await mkdir(path.dirname(target), { recursive: true });

  return { paths, source, target };
}
