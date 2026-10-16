import { z } from "zod";

const filesSchema = z.record(z.string(), z.string().nullable());

const commitSchema = z.strictObject({
  message: z.string().min(1),
  files: filesSchema,
});

const branchStepSchema = z.strictObject({
  branch: z.string(),
  from: z.string().optional(),
  commits: z.array(commitSchema),
});

const threadSchema = z.strictObject({
  id: z.string(),
  pullRequest: z.number(),
  path: z.string(),
  line: z.number(),
  author: z.string(),
  bot: z.boolean(),
  body: z.string(),
  release: z.enum(["initial", "pr-created", "head-changed", "ready"]),
  expected: z.enum(["fix", "decline"]),
});

export const caseSchema = z.strictObject({
  id: z.string().regex(/^[a-z][a-z0-9-]*$/),
  title: z.string(),
  split: z.enum(["train", "test"]),
  tags: z.array(z.string()).min(1),
  prompt: z.string().min(20),
  files: z.record(z.string(), z.string()),
  local: z.array(branchStepSchema),
  pushed: z.array(z.string()),
  upstream: z.array(branchStepSchema),
  checkout: z.string(),
  pullRequests: z.array(
    z.strictObject({
      number: z.number(),
      title: z.string(),
      body: z.string(),
      head: z.string(),
      base: z.string(),
      draft: z.boolean(),
      approved: z.boolean(),
    }),
  ),
  stack: z.strictObject({ trunk: z.string(), branches: z.array(z.string()).min(2) }).nullable(),
  jobs: z.array(
    z.strictObject({ name: z.string(), command: z.array(z.string()).min(1), flakyFailures: z.number().int().min(0) }),
  ),
  hiddenTests: z.record(z.string(), z.string()),
  threads: z.array(threadSchema),
  outcome: z.strictObject({
    readyPullRequests: z.array(z.number()),
    policyJobs: z.array(z.string()),
    template: z.boolean(),
    scopePaths: z.array(z.string()),
  }),
});

export type CaseDefinition = z.infer<typeof caseSchema>;
export type CaseThread = CaseDefinition["threads"][number];
