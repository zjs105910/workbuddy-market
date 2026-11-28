import { z } from "zod";

export const skillRootSchema = z.strictObject({
  id: z.string().regex(/^[a-f0-9]{64}$/),
  directory: z.string(),
  cwd: z.string(),
  scope: z.enum(["global", "repository"]),
  owner: z.enum(["user", "third-party"]),
  destination: z.string(),
  enabled: z.boolean().optional().default(true),
});

export type SkillRoot = z.infer<typeof skillRootSchema>;

export const trackedSkillSchema = z.strictObject({
  id: z.string(),
  rootId: z.string(),
  relativePath: z.string(),
  fingerprint: z.string(),
  kind: z.enum(["amend", "companion"]),
  automatic: z.boolean(),
});

export const maintenanceStateSchema = z.strictObject({
  version: z.literal(1),
  roots: z.array(skillRootSchema).max(64),
  tracked: z.array(trackedSkillSchema),
  assessed: z.record(z.string(), z.string()),
  findings: z.record(z.string(), z.array(z.string())).optional().default({}),
  rejected: z.record(z.string(), z.array(z.string())).optional().default({}),
  libraryReview: z.strictObject({
    catalogs: z.record(z.string(), z.array(z.tuple([z.string(), z.string()]))),
    comparisons: z.array(z.string()),
  }).optional(),
});

export type MaintenanceState = z.infer<typeof maintenanceStateSchema>;

const changeProposalSchema = z.strictObject({
  id: z.uuid(),
  rootId: z.string(),
  skillId: z.string(),
  sourceRelativePath: z.string(),
  sourceFingerprint: z.string(),
  targetRelativePath: z.string(),
  kind: z.enum(["amend", "companion"]),
  before: z.string().nullable(),
  after: z.string(),
  findings: z.array(z.string()),
  status: z.enum(["pending", "applied", "rejected"]),
  createdAt: z.number(),
  inputFingerprint: z.string(),
});

const conflictSourceSchema = z.strictObject({
  rootId: z.string(),
  skillId: z.string(),
  name: z.string(),
  sourceRelativePath: z.string(),
  sourceFingerprint: z.string(),
  passage: z.string().min(1).max(4000),
});

export const conflictProposalSchema = z.strictObject({
  id: z.uuid(),
  kind: z.literal("conflict"),
  sources: z.tuple([conflictSourceSchema, conflictSourceSchema]),
  workflow: z.string().min(1).max(2000),
  decision: z.string().min(1).max(2000),
  findings: z.array(z.string()),
  status: z.enum(["pending", "rejected", "superseded"]),
  createdAt: z.number(),
  inputFingerprint: z.string(),
});

export const proposalSchema = z.discriminatedUnion("kind", [changeProposalSchema, conflictProposalSchema]);
export type SkillChangeProposal = z.infer<typeof changeProposalSchema>;
export type SkillConflictProposal = z.infer<typeof conflictProposalSchema>;
export type SkillProposal = z.infer<typeof proposalSchema>;

export type DiscoveredSkill = {
  readonly valid?: boolean;
  readonly id: string;
  readonly root: SkillRoot;
  readonly relativePath: string;
  readonly raw: string;
  readonly redacted: string;
  readonly fingerprint: string;
  readonly name: string;
  readonly description: string;
  readonly body: string;
};
