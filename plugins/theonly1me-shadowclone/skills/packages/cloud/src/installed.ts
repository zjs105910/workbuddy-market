import { z } from "zod";
import { cloneSchema, type Clone } from "./types";

export type InstalledClone = {
  readonly clone: Clone;
  readonly hasReview: boolean;
};

const contentSchema = z.object({ content: z.string(), encoding: z.literal("base64") });
const repositorySchema = z.object({ default_branch: z.string().min(1) });

async function getJson(options: { readonly route: string; readonly token: string }): Promise<unknown | null> {
  const response = await fetch(`https://api.github.com${options.route}`, {
    headers: {
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      Authorization: `Bearer ${options.token}`,
    },
    signal: AbortSignal.timeout(30_000),
  });

  if (response.status === 404) {
    return null;
  }

  if (!response.ok) {
    throw new Error(`GitHub rejected the request (${response.status}). Check gh auth status and repository access.`);
  }

  return response.json();
}

async function readFile(options: {
  readonly repository: string;
  readonly reference: string;
  readonly filePath: string;
  readonly token: string;
}): Promise<string | null> {
  const data = await getJson({
    route: `/repos/${options.repository}/contents/${options.filePath}?ref=${encodeURIComponent(options.reference)}`,
    token: options.token,
  });

  return data === null ? null : Buffer.from(contentSchema.parse(data).content, "base64").toString("utf8");
}

export function cloneFromRelay(relay: string): Clone {
  const configured = /const config = (\{[\s\S]*?\n\s*\});/.exec(relay)?.[1];

  if (configured === undefined) {
    throw new Error("The clone relay workflow has no configuration block.");
  }

  const parsed = cloneSchema.safeParse(JSON.parse(configured));

  if (!parsed.success) {
    throw new Error("This bot was set up with an earlier Shadowclone version. Run shadowclone bot setup again to update it.");
  }

  return parsed.data;
}

export async function readInstalledClone(options: {
  readonly repository: string;
  readonly token: string;
}): Promise<InstalledClone | null> {
  const repository = repositorySchema.parse(await getJson({ route: `/repos/${options.repository}`, token: options.token }));
  const read = (filePath: string) =>
    readFile({ repository: options.repository, reference: repository.default_branch, filePath, token: options.token });
  const relay = await read(".github/workflows/shadowclone-relay.yml");

  if (relay === null) {
    return null;
  }

  const worker = await read(".github/workflows/shadowclone.yml");

  return { clone: cloneFromRelay(relay), hasReview: worker?.includes("review-analyze:") ?? false };
}
