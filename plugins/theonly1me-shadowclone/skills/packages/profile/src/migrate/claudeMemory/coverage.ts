import { parseProfileBlocks } from "../../profile/parse";
import { parseReference } from "../../references";
import type { ClaudeMemoryFile, ClaudeMemoryManifest } from "./types";

export type ContextFile = {
  readonly relativePath: string;
  readonly content: string;
};

export type MemoryCoverageReview = {
  readonly filename: string;
  readonly claims: readonly {
    readonly claim: string;
    readonly status: "covered" | "excluded" | "conflict" | "missing";
    readonly rationale: string;
    readonly evidence: readonly {
      readonly path: string;
      readonly quote: string;
    }[];
  }[];
};

export function auditMemoryCoverage(options: {
  readonly files: readonly ClaudeMemoryFile[];
  readonly manifest: ClaudeMemoryManifest;
  readonly sources: readonly ContextFile[];
  readonly reviews: readonly MemoryCoverageReview[];
}) {
  if (
    options.files.length === 0 ||
    options.files.length !== options.manifest.files.length ||
    options.manifest.files.some(
      (expected) =>
        !options.files.some(
          (file) =>
            file.filename === expected.filename && file.hash === expected.hash,
        ),
    )
  ) {
    throw new Error("Memory coverage requires the verified migration source");
  }

  return options.files.map((file) => {
    const entry = options.manifest.files.find(
      (candidate) => candidate.filename === file.filename,
    );

    if (!entry) {
      throw new Error("Memory manifest entry is missing");
    }

    const source = options.sources.find(
      (candidate) => candidate.relativePath === entry.destination,
    );
    const reference = source ? parseReference(source.content) : null;

    const rule = source
      ? parseProfileBlocks(source.content).find(
          (block) =>
            block.key === `claude-memory:${file.filename.slice(0, -3)}`,
        )
      : null;

    const unchanged =
      reference?.body === file.body ||
      (rule && "body" in rule && rule.body === file.body);

    if (unchanged && source) {
      return {
        filename: file.filename,
        sourceHash: file.hash,
        claims: [
          {
            claim:
              "Complete source body, including every actionable claim, is preserved.",
            status: "covered" as const,
            rationale:
              "Verified exact redacted body equality against the current destination.",
            evidence: [{ path: source.relativePath, quote: file.body }],
          },
        ],
      };
    }

    if (file.kind === "index") {
      return {
        filename: file.filename,
        sourceHash: file.hash,
        claims: [
          {
            claim: "Memory index routing",
            status: "excluded" as const,
            rationale:
              "Navigation is regenerated from the frozen memory/reference manifests; the index is not an independent fact.",
            evidence: [],
          },
        ],
      };
    }

    const reviewed = options.reviews.find(
      (review) => review.filename === file.filename,
    );

    const claims = reviewed?.claims ?? [
      {
        claim: "Actionable source content",
        status: "missing" as const,
        rationale: "No verified equivalent destination or reviewed exclusion.",
        evidence: [],
      },
    ];

    for (const claim of claims) {
      if (
        !claim.rationale.trim() ||
        !claim.claim.trim() ||
        (claim.status === "covered" && claim.evidence.length === 0)
      ) {
        throw new Error(
          "Memory coverage requires a claim and supporting evidence",
        );
      }

      for (const evidence of claim.evidence) {
        if (
          !evidence.quote.trim() ||
          !options.sources.some(
            (candidate) =>
              candidate.relativePath === evidence.path &&
              candidate.content.includes(evidence.quote),
          )
        ) {
          throw new Error(
            `Memory coverage quotation is not supported: ${file.filename}`,
          );
        }
      }
    }

    return { filename: file.filename, sourceHash: file.hash, claims };
  });
}
