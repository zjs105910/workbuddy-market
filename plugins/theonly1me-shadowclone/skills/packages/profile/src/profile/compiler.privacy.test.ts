import { expect, test } from "bun:test";
import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import type { OriginScope } from "@shadowclone/sessions";
import { compileProfile, renderProfileRule } from "./index";
import type { ProfileRule } from "./index";

test("filesystem guidance crosses the redaction gate before compilation", async () => {
  const profileDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-compiler-private-"),
  );
  const globalDirectory = path.join(profileDirectory, "global");

  await mkdir(globalDirectory, { recursive: true });

  const stripeKeyPrefix = "sk_live";
  const secret = `${stripeKeyPrefix}_1234567890abcdefghijklmnop`;

  const rule: ProfileRule = {
    key: "private-guidance",
    title: "Handle credentials",
    body: `Use ${secret} only in the billing sandbox.`,
    section: "boundaries",
    scope: "global",
    originDirectory: null,
    repositoryName: null,
    source: "user",
    status: "active",
    proposal: null,
    appliesWhen: [`the credential ${secret} appears`],
    evidence: { for: [], against: [] },
    observations: 0,
    lastSeen: "2026-09-09",
    sessions: 0,
    origins: [],
    importReference: null,
  };

  await Bun.write(
    path.join(globalDirectory, "boundaries.md"),
    renderProfileRule(rule),
  );

  const origin: OriginScope = {
    id: "isolated:test",
    directoryName: "isolated--test",
    promotable: false,
  };

  const compilation = await compileProfile({
    input: {
      kind: "directory",
      profileDirectory,
      origin,
      targetRepo: null,
    },
  });

  expect(compilation.markdown).toContain("Handle credentials");
  expect(compilation.markdown).not.toContain(secret);
  expect(compilation.markdown).toContain("[redacted:");
});
