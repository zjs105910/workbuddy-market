import { z } from "zod";
import { sourceIds } from "@shadowclone/core";
import { buildDefinitionSchema } from "./builds/definition";

const locationSchema = z.discriminatedUnion("scope", [
  z.object({
    scope: z.literal("global"),
    originDirectory: z.null(),
    repositoryName: z.null(),
  }),
  z.object({
    scope: z.literal("org"),
    originDirectory: z.string(),
    repositoryName: z.null(),
  }),
  z.object({
    scope: z.literal("project"),
    originDirectory: z.string(),
    repositoryName: z.string(),
  }),
]);

export const learningRuleSchema = z.intersection(
  locationSchema,
  z.object({
    key: z.string(),
    title: z.string(),
    body: z.string().max(2_000_000),
    section: z.enum(["engineering", "workflow", "boundaries"]),
    source: z.enum(["declared", "imported", "mined", "user"]),
    status: z.enum(["active", "candidate", "stale"]),
    proposal: z
      .object({
        kind: z.enum(["revise", "narrow", "retire"]),
        text: z.string(),
      })
      .nullable(),
    appliesWhen: z.array(z.string()),
    evidence: z.object({
      for: z.array(z.string()),
      against: z.array(z.string()),
    }),
    observations: z.number(),
    lastSeen: z.string(),
    sessions: z.number(),
    origins: z.array(z.string()),
    importReference: z
      .object({
        repositoryAliases: z.array(z.string()),
        sourceLocator: z.string(),
      })
      .nullable(),
  }),
);

export const learningRecordSchema = z.strictObject({
  rule: learningRuleSchema,
  kind: z.enum(["guidance", "context"]),
  sourceHash: z.string().nullable(),
  sourceLocator: z.string().nullable(),
  retirementRequested: z.literal(true).optional(),
  captureSources: z.array(z.enum(sourceIds)).optional(),
  provenanceComplete: z.boolean().optional(),
});

export const environmentRepositorySchema = z.strictObject({
  directory: z.string(),
  originDirectory: z.string(),
  repositoryName: z.string(),
});

export const artifactSchema = z.strictObject({
  filePath: z.string(),
  fingerprint: z.string(),
  original: z.string().nullable(),
  kind: z.enum(["skill", "instructions", "resource"]),
  encoding: z.enum(["utf8", "base64"]).optional(),
  scope: z.string(),
  name: z.string(),
  description: z.string(),
  appliesWhen: z.string().optional(),
  learningKeys: z.array(z.string()),
  buildId: z.string().optional(),
  buildEntryId: z.string().optional(),
});

export const dispositionSchema = z.strictObject({
  scope: z.string().optional(),
  key: z.string(),
  inputFingerprint: z.string(),
  status: z.enum(["published", "covered", "excluded", "pending"]),
  publishedAt: z.number().optional(),
  reason: z.string(),
  destinations: z.array(z.string()),
  fingerprints: z.record(z.string(), z.string()).optional(),
});

export const environmentSchema = z.strictObject({
  version: z.literal(1),
  phase: z.enum(["preparing", "active"]),
  automatic: z.boolean(),
  records: z.array(learningRecordSchema),
  repositories: z.array(environmentRepositorySchema),
  artifacts: z.array(artifactSchema),
  dispositions: z.array(dispositionSchema),
  memoryHashes: z.record(z.string(), z.string()),
  rejected: z.array(z.string()),
  facts: z
    .array(
      z.strictObject({
        scope: z.string(),
        text: z.string(),
        learningKeys: z.array(z.string()),
      }),
    )
    .default([]),
  baselineDirectory: z.string().nullable(),
  rejectionText: z.string().default(""),
  builds: z.array(buildDefinitionSchema).default([]),
});

export type LearningRecord = z.infer<typeof learningRecordSchema>;

export type EnvironmentState = z.infer<typeof environmentSchema>;

export type EnvironmentRepository = z.infer<typeof environmentRepositorySchema>;

export type EnvironmentArtifact = z.infer<typeof artifactSchema>;

export const emptyEnvironment: EnvironmentState = {
  version: 1,
  phase: "preparing",
  automatic: false,
  records: [],
  repositories: [],
  artifacts: [],
  dispositions: [],
  memoryHashes: {},
  rejected: [],
  facts: [],
  baselineDirectory: null,
  rejectionText: "",
  builds: [],
};
