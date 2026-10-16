import path from "node:path";
import type { RepositoryIdentity } from "@shadowclone/sessions";
import {
  referenceRelativePath,
  renderReference,
  type ReferenceRecord,
} from "../../references";
import { profileRulePath, renderProfileRule } from "../../profile";
import type {
  ClaudeFeedbackDecision,
  ClaudeMemoryFile,
  ClaudeMemoryManifestFile,
} from "./types";

function titleFromFile(file: ClaudeMemoryFile): string {
  const prefix = `${file.kind}_`;
  const name = (file.name || file.filename.slice(0, -3))
    .replace(prefix, "")
    .replaceAll(/[_-]+/g, " ")
    .trim();

  return name.length === 0
    ? file.filename
    : `${name[0]?.toUpperCase() ?? ""}${name.slice(1)}`;
}

export function referenceFromMemory(options: {
  readonly file: ClaudeMemoryFile;
  readonly repository: RepositoryIdentity;
  readonly now: number;
}): {
  readonly record: ReferenceRecord;
  readonly relativePath: string;
  readonly content: string;
} {
  const key = options.file.filename.slice(0, -3).toLowerCase();

  const record: ReferenceRecord = {
    schema: 1,
    key,
    title: titleFromFile(options.file),
    summary: options.file.description || options.file.body.slice(0, 500),
    tags: key.split(/[_-]+/).filter(Boolean).slice(0, 16),
    scope: "project",
    originDirectory: options.repository.origin.directoryName,
    repositoryName: options.repository.profileFileName ?? "repository",
    source:
      options.file.kind === "project"
        ? "claude-project-memory"
        : "claude-memory",
    sourceLocator: options.file.filename,
    updatedAt: /^\d{4}-\d{2}-\d{2}T/.test(options.file.modified)
      ? options.file.modified
      : new Date(options.now).toISOString(),
    body: options.file.body,
  };

  return {
    record,
    relativePath: referenceRelativePath(record),
    content: renderReference(record),
  };
}

export function ruleFromMemory(options: {
  readonly file: ClaudeMemoryFile;
  readonly decision: Extract<
    ClaudeFeedbackDecision,
    { readonly disposition: "rule" }
  >;
  readonly repository: RepositoryIdentity;
}): {
  readonly relativePath: string;
  readonly content: string;
  readonly key: string;
} {
  const location =
    options.decision.scope === "global"
      ? {
          scope: "global" as const,
          originDirectory: null,
          repositoryName: null,
        }
      : {
          scope: "project" as const,
          originDirectory: options.repository.origin.directoryName,
          repositoryName: options.repository.profileFileName ?? "repository",
        };

  const rule = {
    key: `claude-memory:${options.file.filename.slice(0, -3)}`,
    title: options.decision.title,
    body: options.file.body,
    section: options.decision.section,
    ...location,
    source: "user" as const,
    status: "active" as const,
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: 0,
    lastSeen: "imported",
    sessions: 0,
    origins: [],
    importReference: null,
  };

  return {
    relativePath: profileRulePath(rule),
    content: renderProfileRule(rule),
    key: rule.key,
  };
}

export function manifestEntry(options: {
  readonly file: ClaudeMemoryFile;
  readonly disposition: ClaudeMemoryManifestFile["disposition"];
  readonly destination?: string;
  readonly reason?: ClaudeMemoryManifestFile["reason"];
}): ClaudeMemoryManifestFile {
  return {
    filename: options.file.filename,
    hash: options.file.hash,
    bytes: options.file.bytes,
    kind: options.file.kind,
    disposition: options.disposition,
    ...(options.destination === undefined
      ? {}
      : { destination: path.normalize(options.destination) }),
    ...(options.reason === undefined ? {} : { reason: options.reason }),
  };
}
