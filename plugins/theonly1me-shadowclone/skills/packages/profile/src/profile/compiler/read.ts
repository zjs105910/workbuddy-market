import path from "node:path";
import { materializeSnapshot } from "@shadowclone/redact";
import { maximumProfileBytes } from "@shadowclone/core";
import type { OriginScope } from "@shadowclone/sessions";
import { splitProfileBlocks } from "../blocks";
import { effectiveProfileStatus } from "../evidence";
import { parseProfileBlocks } from "../parse";
import { isSafeProfileSegment } from "../render";
import type { ExistingProfileBlock, ProfileRule } from "../types";
import type { ReferenceSearchResult } from "../../references";
import { profileBlockMetadata, stripProfileMetadata } from "../visible";
import type { CompilerBlock } from "./types";

const scopeFilenames = [
  "identity.md",
  "engineering.md",
  "workflow.md",
  "boundaries.md",
] as const;

export function profileScopePaths(options: {
  readonly origin: OriginScope | null;
  readonly targetRepo: string | null;
  readonly scope?: "global" | "scoped" | "combined";
}): readonly string[] {
  const globalPaths =
    options.scope === "scoped"
      ? []
      : scopeFilenames.map((filename) => path.join("global", filename));

  if (
    options.scope === "global" ||
    options.origin === null ||
    !isSafeProfileSegment(options.origin.directoryName)
  ) {
    return globalPaths;
  }

  const organization = path.join("org", options.origin.directoryName);
  const organizationPaths = scopeFilenames.map((filename) =>
    path.join(organization, filename),
  );
  const targetRepo = options.targetRepo;

  if (targetRepo === null || !isSafeProfileSegment(targetRepo)) {
    return [...globalPaths, ...organizationPaths];
  }

  return [
    ...globalPaths,
    ...organizationPaths,
    path.join(organization, "projects", `${targetRepo}.md`),
  ];
}

function compilerBlock(options: {
  readonly block: ExistingProfileBlock;
  readonly redactedBlock: string;
  readonly scope: "global" | "org" | "project";
}): CompilerBlock {
  const visible = stripProfileMetadata(options.redactedBlock);

  if (options.block.key === null) {
    return {
      kind: "rule",
      scope: options.scope,
      ruleKey: null,
      referenceKey: null,
      source: "user",
      status: "active",
      observations: 0,
      visible,
      appliesWhen: [],
    };
  }

  return {
    kind: "rule",
    scope: options.scope,
    ruleKey: options.block.key,
    referenceKey: null,
    source: options.block.source,
    status: effectiveProfileStatus(options.block),
    observations: options.block.observations,
    visible,
    appliesWhen: profileBlockMetadata(options.redactedBlock).appliesWhen,
  };
}

async function readScopeFile(options: {
  readonly filePath: string;
  readonly profileDirectory: string;
}): Promise<readonly CompilerBlock[]> {
  const snapshot = await materializeSnapshot({
    filePath: options.filePath,
    roots: [options.profileDirectory],
    maximumBytes: maximumProfileBytes,
    parse: parseProfileBlocks,
  });

  if (snapshot === null) {
    return [];
  }

  const rawBlocks = snapshot.parsed;
  const redactedBlocks = splitProfileBlocks(snapshot.redacted);

  if (rawBlocks.length !== redactedBlocks.length) {
    return [];
  }

  return rawBlocks.flatMap((block, index) => {
    const redactedBlock = redactedBlocks[index];
    const relativePath = path.relative(
      options.profileDirectory,
      options.filePath,
    );
    const scope = relativePath.startsWith(`global${path.sep}`)
      ? ("global" as const)
      : relativePath.includes(`${path.sep}projects${path.sep}`)
        ? ("project" as const)
        : ("org" as const);

    return redactedBlock === undefined
      ? []
      : [compilerBlock({ block, redactedBlock, scope })];
  });
}

export async function readCompilerBlocks(options: {
  readonly profileDirectory: string;
  readonly origin: OriginScope | null;
  readonly targetRepo: string | null;
  readonly scope?: "global" | "scoped" | "combined";
}): Promise<readonly CompilerBlock[]> {
  const files = await Promise.all(
    profileScopePaths({
      origin: options.origin,
      targetRepo: options.targetRepo,
      scope: options.scope,
    }).map((relativePath) =>
      readScopeFile({
        filePath: path.join(options.profileDirectory, relativePath),
        profileDirectory: options.profileDirectory,
      }),
    ),
  );

  return files.flat();
}

export function compilerBlocksFromRules(
  rules: readonly ProfileRule[],
): readonly CompilerBlock[] {
  return rules.map((rule) => ({
    kind: "rule",
    scope: rule.scope,
    ruleKey: rule.key,
    referenceKey: null,
    source: rule.source,
    status: rule.status,
    observations: rule.observations,
    visible:
      rule.body.length === 0
        ? `## ${rule.title}`
        : `## ${rule.title}\n\n${rule.body}`,
    appliesWhen: rule.appliesWhen,
  }));
}

export function compilerBlocksFromReferences(
  references: readonly ReferenceSearchResult[],
): readonly CompilerBlock[] {
  return references
    .filter(({ record }) => record.source !== "claude-project-memory")
    .map(({ record }) => ({
      kind: "reference",
      scope: record.scope,
      ruleKey: null,
      referenceKey: record.key,
      source: "reference",
      status: "active",
      observations: 0,
      visible: `Reference \`${record.key}\`: **${record.title}**. ${record.summary}`,
      appliesWhen: [],
    }));
}
