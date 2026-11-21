import { encodeProfileMetadata, uniqueProfileEvidence } from "./metadata";
import type { ProfileRule } from "./types";

export function profileFingerprint(value: string): string {
  return new Bun.CryptoHasher("sha256")
    .update(value)
    .digest("hex")
    .slice(0, 16);
}

export function createProfileRuleKey(): string {
  return crypto.randomUUID();
}

export function profileRulePath(rule: ProfileRule): string {
  if (rule.scope === "global") {
    return `global/${rule.section}.md`;
  }

  if (!isSafeProfileSegment(rule.originDirectory)) {
    throw new Error("Profile rule has an invalid origin directory");
  }

  if (rule.scope === "project") {
    if (!isSafeProfileSegment(rule.repositoryName)) {
      throw new Error("Profile rule has an invalid repository name");
    }

    return `org/${rule.originDirectory}/projects/${rule.repositoryName}.md`;
  }

  return `org/${rule.originDirectory}/${rule.section}.md`;
}

export function isSafeProfileSegment(value: string): boolean {
  return (
    value.length > 0 &&
    value !== "." &&
    value !== ".." &&
    !value.includes("/") &&
    !value.includes("\\")
  );
}

export function renderProfileRule(rule: ProfileRule): string {
  const visible = `## ${rule.title}\n\n${rule.body}`;
  const evidence = uniqueProfileEvidence(rule.evidence);

  const metadata = {
    schema: 1,
    key: rule.key,
    source: rule.source,
    status: rule.status,
    proposal: rule.proposal,
    "applies-when": [...rule.appliesWhen],
    supports: evidence.for.length,
    contradicts: evidence.against.length,
    evidence,
    observations: rule.observations,
    "last-seen": rule.lastSeen,
    sessions: rule.sessions,
    origins: [...rule.origins],
    scope: rule.scope,
    "import-reference": rule.importReference,
    fingerprint: profileFingerprint(visible),
  };

  return `${visible}\n\n<!-- shadowclone: ${encodeProfileMetadata(metadata)} -->`;
}
