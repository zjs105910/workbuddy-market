import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { OriginScope } from "@shadowclone/sessions";
import { originDirectoryName } from "@shadowclone/sessions";
import { compileProfile, renderProfileRule } from "./index";
import type { ProfileRule } from "./index";

function origin(owner: string): OriginScope {
  return {
    id: `github.com/${owner}`,
    directoryName: originDirectoryName(`github.com/${owner}`),
    promotable: true,
  };
}

function rule(options: {
  readonly owner: string;
  readonly title: string;
}): ProfileRule {
  return {
    key: options.title.toLowerCase().replaceAll(" ", "-"),
    title: options.title,
    body: `Rule for ${options.owner}.`,
    section: "workflow",
    scope: "org",
    originDirectory: originDirectoryName(`github.com/${options.owner}`),
    repositoryName: null,
    source: "mined",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [`event:${options.owner}`], against: [] },
    observations: 3,
    lastSeen: "2026-09-05",
    sessions: 2,
    origins: [`github.com/${options.owner}`],
    importReference: null,
  };
}

test("compiles global and matching organization rules only", async () => {
  const profileDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-compiler-scope-"),
  );

  const globalRule = {
    ...rule({ owner: "acme", title: "Plan first" }),
    scope: "global" as const,
    originDirectory: null,
    repositoryName: null,
  };

  await mkdir(path.join(profileDirectory, "global"), { recursive: true });
  await mkdir(
    path.join(profileDirectory, "org", "github.com--acme--936913df4a5c268b"),
    {
      recursive: true,
    },
  );
  await mkdir(
    path.join(profileDirectory, "org", "github.com--other--2cf88805dc6fdfe1"),
    {
      recursive: true,
    },
  );
  await Bun.write(
    path.join(profileDirectory, "global", "workflow.md"),
    renderProfileRule(globalRule),
  );
  await Bun.write(
    path.join(
      profileDirectory,
      "org",
      "github.com--acme--936913df4a5c268b",
      "workflow.md",
    ),
    renderProfileRule(rule({ owner: "acme", title: "Use Bun" })),
  );
  await Bun.write(
    path.join(
      profileDirectory,
      "org",
      "github.com--other--2cf88805dc6fdfe1",
      "workflow.md",
    ),
    renderProfileRule(rule({ owner: "other", title: "Use Cargo" })),
  );

  const compilation = await compileProfile({
    input: {
      kind: "directory",
      profileDirectory,
      origin: origin("acme"),
      targetRepo: null,
    },
  });

  expect(compilation.markdown).toContain("Plan first");
  expect(compilation.markdown).toContain("Use Bun");
  expect(compilation.markdown).not.toContain("Use Cargo");
  expect(compilation.markdown).not.toContain("<!-- shadowclone:");
});

test("admits only the exact project file for the active repository", async () => {
  const profileDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-compiler-project-"),
  );

  const projects = path.join(
    profileDirectory,
    "org",
    "github.com--acme--936913df4a5c268b",
    "projects",
  );

  await mkdir(projects, { recursive: true });

  const projectRule = (name: string): ProfileRule => ({
    ...rule({ owner: "acme", title: `Guidance for ${name}` }),
    scope: "project",
    originDirectory: "github.com--acme--936913df4a5c268b",
    repositoryName: name,
  });

  await Bun.write(
    path.join(projects, "platform.md"),
    renderProfileRule(projectRule("platform")),
  );
  await Bun.write(
    path.join(projects, "console.md"),
    renderProfileRule(projectRule("console")),
  );

  const compilation = await compileProfile({
    input: {
      kind: "directory",
      profileDirectory,
      origin: origin("acme"),
      targetRepo: "platform",
    },
  });

  expect(compilation.markdown).toContain("Guidance for platform");
  expect(compilation.markdown).not.toContain("Guidance for console");
});
