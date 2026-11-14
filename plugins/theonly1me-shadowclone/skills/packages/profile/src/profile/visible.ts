import { profileMetadataSchema } from "./metadata";
import type { ProfileRule } from "./types";

const metadataPattern = /\n\n<!-- shadowclone: [^\n]+ -->\s*$/;
const metadataCapture = /\n\n<!-- shadowclone: ([^\n]+) -->\s*$/;

export function stripProfileMetadata(block: string): string {
  return block.replace(metadataPattern, "").trim();
}

export function profileVisibleParts(block: string): {
  readonly title: string;
  readonly body: string;
} {
  const [heading, ...body] = stripProfileMetadata(block).split("\n");

  return {
    title: heading?.replace(/^#+\s*/, "").trim() ?? "",
    body: body.join("\n").trim(),
  };
}

export function profileBlockMetadata(block: string): {
  readonly appliesWhen: readonly string[];
  readonly proposal: ProfileRule["proposal"];
} {
  const match = block.match(metadataCapture);

  if (!match?.[1]) {
    return { appliesWhen: [], proposal: null };
  }

  let value: unknown;

  try {
    value = JSON.parse(match[1]);
  } catch {
    return { appliesWhen: [], proposal: null };
  }

  const parsed = profileMetadataSchema.safeParse(value);

  return parsed.success
    ? {
        appliesWhen: parsed.data["applies-when"],
        proposal: parsed.data.proposal,
      }
    : { appliesWhen: [], proposal: null };
}
