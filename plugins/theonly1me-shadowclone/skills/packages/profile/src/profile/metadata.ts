import { z } from "zod";
import type { ProfileEvidence } from "./types";

const opaqueHashSchema = z.string().regex(/^[a-f0-9]{64}$/);

export const profileImportReferenceSchema = z.object({
  repositoryAliases: z.array(opaqueHashSchema).min(1),
  sourceLocator: opaqueHashSchema,
});

const profileSourceSchema = z.enum(["declared", "imported", "mined", "user"]);
const profileStatusSchema = z.enum(["active", "candidate", "stale"]);

const profileProposalSchema = z
  .object({
    kind: z.enum(["revise", "narrow", "retire"]),
    text: z.string(),
  })
  .nullable();

const profileEvidenceSchema = z.object({
  for: z.array(z.string()),
  against: z.array(z.string()),
});

const profileRuleFieldsSchema = z.object({
  key: z.string().min(1),
  title: z.string(),
  body: z.string(),
  section: z.enum(["engineering", "workflow", "boundaries"]),
  source: profileSourceSchema,
  status: profileStatusSchema,
  proposal: profileProposalSchema,
  appliesWhen: z.array(z.string()),
  evidence: profileEvidenceSchema,
  observations: z.number().int().nonnegative(),
  lastSeen: z.string(),
  sessions: z.number().int().nonnegative(),
  origins: z.array(z.string()),
  importReference: profileImportReferenceSchema
    .nullable()
    .optional()
    .default(null),
});

const profileRuleLocationSchema = z.discriminatedUnion("scope", [
  z.object({
    scope: z.literal("global"),
    originDirectory: z.null(),
    repositoryName: z.null().optional().default(null),
  }),
  z.object({
    scope: z.literal("org"),
    originDirectory: z.string().min(1),
    repositoryName: z.null().optional().default(null),
  }),
  z.object({
    scope: z.literal("project"),
    originDirectory: z.string().min(1),
    repositoryName: z.string().min(1),
  }),
]);

export const profileRuleSchema = profileRuleFieldsSchema.and(
  profileRuleLocationSchema,
);

export const profileMetadataSchema = z.object({
  schema: z.literal(1),
  key: z.string().min(1),
  source: profileSourceSchema,
  status: profileStatusSchema,
  proposal: profileProposalSchema,
  "applies-when": z.array(z.string()),
  supports: z.number().int().nonnegative(),
  contradicts: z.number().int().nonnegative(),
  evidence: profileEvidenceSchema,
  observations: z.number().int().nonnegative(),
  "last-seen": z.string(),
  sessions: z.number().int().nonnegative(),
  origins: z.array(z.string()),
  scope: z.enum(["global", "org", "project"]),
  "import-reference": profileImportReferenceSchema
    .nullable()
    .optional()
    .default(null),
  fingerprint: z.string().min(1),
});

export function uniqueProfileEvidence(
  evidence: ProfileEvidence,
): ProfileEvidence {
  return {
    for: [...new Set(evidence.for)],
    against: [...new Set(evidence.against)],
  };
}

export function encodeProfileMetadata(value: object): string {
  return JSON.stringify(value).replaceAll("--", "\\u002d\\u002d");
}
