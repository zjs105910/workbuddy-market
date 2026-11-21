import { z } from "zod";
import { readEffectiveConfig, runHostCommand } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { redactSecrets } from "@shadowclone/redact";

export type WritingKind = "pull-request" | "review" | "commit";
export type Writing = { readonly kind: WritingKind; readonly text: string };
export type HostRunner = typeof runHostCommand;

export const writingLimits = { itemCharacters: 1_200, totalCharacters: 24_000, perKind: 40 } as const;

const writingQuery = `query {
  viewer {
    login
    pullRequests(first: 40, orderBy: {field: CREATED_AT, direction: DESC}) {
      nodes { title body headRefName }
    }
    contributionsCollection {
      pullRequestReviewContributions(first: 40, orderBy: {direction: DESC}) {
        nodes { pullRequestReview { body comments(first: 10) { nodes { body } } } }
      }
    }
  }
}`;

const writingResponseSchema = z.object({
  data: z.object({
    viewer: z.object({
      login: z.string().min(1),
      pullRequests: z.object({
        nodes: z.array(z.object({ title: z.string(), body: z.string().nullable(), headRefName: z.string() }).nullable()),
      }),
      contributionsCollection: z.object({
        pullRequestReviewContributions: z.object({
          nodes: z.array(
            z
              .object({
                pullRequestReview: z
                  .object({
                    body: z.string().nullable(),
                    comments: z.object({ nodes: z.array(z.object({ body: z.string() }).nullable()) }),
                  })
                  .nullable(),
              })
              .nullable(),
          ),
        }),
      }),
    }),
  }),
});

const commitsSchema = z.array(z.object({ commit: z.object({ message: z.string() }) }));

const agentBranch = /^(codex|claude|cursor)\//i;
const agentText =
  /generated with \[?claude|co-authored-by:\s*(claude|codex|cursor)|\u{1F916}|\b(created|written|drafted) (with|by) (claude|codex|cursor|an? (ai|coding) agent)\b/iu;
const machineText = /^(chore(\(.+\))?: release\b|merge (pull request|branch|remote-tracking)\b|revert ")/i;

function cleaned(text: string): string {
  return text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function eligibleWriting(options: { readonly kind: WritingKind; readonly text: string; readonly branch?: string }): Writing | null {
  if (options.branch && agentBranch.test(options.branch)) return null;
  if (agentText.test(options.text) || machineText.test(options.text.trim())) return null;

  const text = redactSecrets({ text: cleaned(options.text) }).slice(0, writingLimits.itemCharacters);

  return text.length >= 20 ? { kind: options.kind, text } : null;
}

function balanced(writing: readonly Writing[]): readonly Writing[] {
  const queues = (["pull-request", "review", "commit"] as const).map((kind) =>
    writing.filter((entry) => entry.kind === kind).slice(0, writingLimits.perKind),
  );
  const chosen: Writing[] = [];
  let total = 0;

  for (let index = 0; index < writingLimits.perKind; index += 1) {
    for (const queue of queues) {
      const entry = queue[index];

      if (!entry || total + entry.text.length > writingLimits.totalCharacters) continue;

      chosen.push(entry);
      total += entry.text.length;
    }
  }

  return chosen;
}

async function ghJson(options: { readonly run: HostRunner; readonly cwd: string; readonly arguments: readonly string[]; readonly signal?: AbortSignal }): Promise<unknown> {
  const result = await options.run({ arguments: ["gh", ...options.arguments], cwd: options.cwd, timeoutSeconds: 30, signal: options.signal });

  if (result.exitCode !== 0) {
    throw new Error(`gh could not read your GitHub writing: ${redactSecrets({ text: result.stderr }).slice(0, 300)}`);
  }

  return JSON.parse(result.stdout);
}

export async function githubWritingAllowed(options: { readonly paths: ProjectPaths }): Promise<boolean> {
  const { config } = await readEffectiveConfig({ configPath: options.paths.configFile, managedConfigPath: options.paths.managedConfigFile });

  return config.sources["github-writing"];
}

export async function collectWriting(options: {
  readonly paths: ProjectPaths;
  readonly cwd: string;
  readonly run?: HostRunner;
  readonly signal?: AbortSignal;
}): Promise<readonly Writing[]> {
  if (!(await githubWritingAllowed(options))) {
    throw new Error("Allow Shadowclone to read your GitHub writing before you capture your voice");
  }

  const run = options.run ?? runHostCommand;
  const { viewer } = writingResponseSchema.parse(
    await ghJson({ ...options, run, arguments: ["api", "graphql", "-f", `query=${writingQuery}`] }),
  ).data;
  const commits = commitsSchema.parse(
    await ghJson({
      ...options,
      run,
      arguments: ["search", "commits", "--author", viewer.login, "--sort", "committer-date", "--limit", "60", "--json", "commit"],
    }),
  );
  const writing = [
    ...viewer.pullRequests.nodes.flatMap((pull) =>
      pull ? [eligibleWriting({ kind: "pull-request", text: `${pull.title}\n\n${pull.body ?? ""}`, branch: pull.headRefName })] : [],
    ),
    ...viewer.contributionsCollection.pullRequestReviewContributions.nodes.flatMap((node) => {
      const review = node?.pullRequestReview;

      return review
        ? [review.body ?? "", ...review.comments.nodes.map((comment) => comment?.body ?? "")].map((text) =>
            eligibleWriting({ kind: "review", text }),
          )
        : [];
    }),
    ...commits.map((entry) => eligibleWriting({ kind: "commit", text: entry.commit.message })),
  ];

  return balanced(writing.filter((entry): entry is Writing => entry !== null));
}
