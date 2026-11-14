import { expect, test } from "bun:test";
import { auditMemoryCoverage } from "./coverage";
import type { ClaudeMemoryFile, ClaudeMemoryManifest } from "./types";

const file: ClaudeMemoryFile = {
  filename: "feedback_style.md",
  sourcePath: "/memory/feedback_style.md",
  kind: "feedback",
  hash: "verified",
  bytes: 40,
  name: "style",
  description: "Naming",
  modified: "2026-09-20",
  body: "Use complete names.",
};

const manifest: ClaudeMemoryManifest = {
  schema: 1,
  repositoryId: "repository",
  sourceDirectory: "/memory",
  createdAt: "2026-09-20T00:00:00.000Z",
  files: [
    {
      filename: file.filename,
      hash: file.hash,
      bytes: file.bytes,
      kind: file.kind,
      disposition: "covered",
      reason: "skill-covered",
    },
  ],
};

test("covered migration labels alone never establish parity", () => {
  const result = auditMemoryCoverage({
    files: [file],
    manifest,
    sources: [],
    reviews: [],
  });

  expect(result[0]?.claims[0]?.status).toBe("missing");
});

test("coverage requires matching source hashes and quoted destination evidence", () => {
  expect(() =>
    auditMemoryCoverage({
      files: [{ ...file, hash: "changed" }],
      manifest,
      sources: [],
      reviews: [],
    }),
  ).toThrow("verified migration source");

  const review = {
    filename: file.filename,
    claims: [
      {
        claim: "Full names",
        status: "covered" as const,
        rationale: "Same rule in skill",
        evidence: [{ path: "skills/clean-code", quote: file.body }],
      },
    ],
  };

  expect(() =>
    auditMemoryCoverage({
      files: [file],
      manifest,
      sources: [],
      reviews: [review],
    }),
  ).toThrow("not supported");
  expect(
    auditMemoryCoverage({
      files: [file],
      manifest,
      sources: [{ relativePath: "skills/clean-code", content: file.body }],
      reviews: [review],
    })[0]?.claims[0]?.status,
  ).toBe("covered");
});
