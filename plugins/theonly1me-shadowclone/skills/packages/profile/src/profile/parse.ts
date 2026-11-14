import { profileMetadataSchema, uniqueProfileEvidence } from "./metadata";
import { profileFingerprint } from "./render";
import { splitProfileBlocks } from "./blocks";
import type {
  ExistingProfileBlock,
  ExistingProfileRule,
  ProfileScope,
} from "./types";

function readLegacyValue(options: {
  readonly metadata: string;
  readonly name: string;
}): string | null {
  const prefix = `${options.name}=`;
  const value = options.metadata
    .split(/\s+/)
    .find((entry) => entry.startsWith(prefix));

  return value?.slice(prefix.length) ?? null;
}

function manualBlock(content: string): ExistingProfileBlock {
  return {
    key: null,
    content: content.trim(),
    edited: true,
    source: "user",
    status: "active",
  };
}

function visibleParts(visible: string): {
  readonly title: string;
  readonly body: string;
} {
  const [heading, ...body] = visible.split("\n");

  return {
    title: heading?.replace(/^#+\s*/, "").trim() ?? "",
    body: body.join("\n").trim(),
  };
}

function parseCurrent(options: {
  readonly block: string;
  readonly metadata: string;
  readonly visible: string;
}): ExistingProfileBlock | null {
  let decoded: unknown;

  try {
    decoded = JSON.parse(options.metadata);
  } catch {
    return null;
  }

  const result = profileMetadataSchema.safeParse(decoded);

  if (!result.success) {
    return null;
  }

  const evidence = uniqueProfileEvidence(result.data.evidence);

  if (
    result.data.supports !== evidence.for.length ||
    result.data.contradicts !== evidence.against.length
  ) {
    return null;
  }

  const edited =
    profileFingerprint(options.visible) !== result.data.fingerprint;
  const parts = visibleParts(options.visible);

  return {
    key: result.data.key,
    ...parts,
    source: edited ? "user" : result.data.source,
    status: edited ? "active" : result.data.status,
    proposal: edited ? null : result.data.proposal,
    appliesWhen: result.data["applies-when"],
    evidence,
    observations: result.data.observations,
    lastSeen: result.data["last-seen"],
    sessions: result.data.sessions,
    origins: result.data.origins,
    scope: result.data.scope,
    importReference: result.data["import-reference"],
    fingerprint: result.data.fingerprint,
    content: options.block.trim(),
    edited,
    legacy: false,
  };
}

function legacyNumber(options: {
  readonly metadata: string;
  readonly name: string;
}): number {
  const value = Number(readLegacyValue(options));

  return Number.isFinite(value) ? value : 0;
}

function parseLegacy(options: {
  readonly block: string;
  readonly metadata: string;
  readonly visible: string;
}): ExistingProfileBlock {
  const key = readLegacyValue({ metadata: options.metadata, name: "key" });
  const fingerprint = readLegacyValue({
    metadata: options.metadata,
    name: "fingerprint",
  });

  if (key === null || fingerprint === null) {
    return manualBlock(options.block);
  }

  const edited = profileFingerprint(options.visible) !== fingerprint;
  const scopeValue = readLegacyValue({
    metadata: options.metadata,
    name: "scope",
  });
  const scope: ProfileScope = scopeValue === "global" ? "global" : "org";
  const origins =
    readLegacyValue({ metadata: options.metadata, name: "origins" })
      ?.split(",")
      .filter((value) => value.length > 0) ?? [];

  return {
    key,
    ...visibleParts(options.visible),
    source: edited ? "user" : "mined",
    status: "active",
    proposal: null,
    appliesWhen: [],
    evidence: { for: [], against: [] },
    observations: legacyNumber({
      metadata: options.metadata,
      name: "observations",
    }),
    lastSeen:
      readLegacyValue({ metadata: options.metadata, name: "last-seen" }) ??
      "unknown",
    sessions: legacyNumber({
      metadata: options.metadata,
      name: "sessions",
    }),
    origins,
    scope,
    importReference: null,
    fingerprint,
    content: options.block.trim(),
    edited,
    legacy: true,
  };
}

function parseBlock(block: string): ExistingProfileBlock {
  const metadataMatch = block.match(/\n\n<!-- shadowclone: ([^\n]+) -->\s*$/);
  const metadata = metadataMatch?.[1];

  if (!metadata || metadataMatch.index === undefined) {
    return manualBlock(block);
  }

  const visible = block.slice(0, metadataMatch.index).trim();

  return (
    parseCurrent({ block, metadata, visible }) ??
    parseLegacy({ block, metadata, visible })
  );
}

export function parseProfileBlocks(
  text: string,
): readonly ExistingProfileBlock[] {
  return splitProfileBlocks(text).map(parseBlock);
}

export function parseProfileRules(
  text: string,
): readonly ExistingProfileRule[] {
  return parseProfileBlocks(text).filter((block) => block.key !== null);
}
