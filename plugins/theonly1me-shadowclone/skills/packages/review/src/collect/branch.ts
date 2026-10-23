import path from "node:path";
import { pullFactsSchema, type PullFacts } from "../types";
import { readGit } from "./git";

const githubRemote = /github\.com[:/]([\w.-]+)\/([\w.-]+?)(?:\.git)?\/?$/;
const maximumBodyLength = 65_536;

async function gitLine(options: { readonly checkout: string; readonly arguments: readonly string[] }): Promise<string> {
  return (await readGit(options)).trim();
}

export async function branchRepositoryName(checkout: string): Promise<string> {
  const remote = await gitLine({ checkout, arguments: ["remote", "get-url", "origin"] }).catch(() => "");
  const [, owner, name] = githubRemote.exec(remote) ?? [];

  return owner && name ? `${owner}/${name}` : `local/${path.basename(checkout).replace(/[^\w.-]/g, "-")}`;
}

async function defaultBase(checkout: string): Promise<string> {
  return gitLine({ checkout, arguments: ["rev-parse", "--abbrev-ref", "origin/HEAD"] }).catch(() => {
    throw new Error("This checkout has no origin/HEAD. Name the base with --base, for example --base main.");
  });
}

async function commitMessages(options: { readonly checkout: string; readonly baseSha: string; readonly headSha: string }): Promise<{ readonly title: string; readonly body: string }> {
  const { checkout, baseSha, headSha } = options;
  const count = Number(await gitLine({ checkout, arguments: ["rev-list", "--count", `${baseSha}..${headSha}`] }));
  const title = await gitLine({ checkout, arguments: ["log", "-1", "--format=%s", headSha] });
  const body =
    count === 1
      ? await gitLine({ checkout, arguments: ["log", "-1", "--format=%b", headSha] })
      : await gitLine({ checkout, arguments: ["log", "--format=%B", `${baseSha}..${headSha}`] });

  return { title: title.slice(0, 1000), body: body.slice(0, maximumBodyLength) };
}

export async function readBranchFacts(options: {
  readonly checkout: string;
  readonly repository: string;
  readonly base: string | null;
}): Promise<PullFacts> {
  const { checkout } = options;
  const baseRefName = options.base ?? (await defaultBase(checkout));
  const headSha = await gitLine({ checkout, arguments: ["rev-parse", "--verify", "HEAD^{commit}"] });
  const baseCommit = await gitLine({ checkout, arguments: ["rev-parse", "--verify", "--end-of-options", `${baseRefName}^{commit}`] }).catch(() => {
    throw new Error(`git cannot find the base ${baseRefName}. Name an existing branch or commit with --base.`);
  });
  const baseSha = await gitLine({ checkout, arguments: ["merge-base", baseCommit, headSha] });

  if (baseSha === headSha) {
    throw new Error(`The branch has no commits after ${baseRefName}. Commit the change, or name another base with --base.`);
  }

  return pullFactsSchema.parse({
    repository: options.repository,
    number: null,
    ...(await commitMessages({ checkout, baseSha, headSha })),
    baseRefName,
    baseSha,
    headSha,
  });
}

export async function hasUncommittedChanges(checkout: string): Promise<boolean> {
  return (await gitLine({ checkout, arguments: ["status", "--porcelain", "--untracked-files=normal"] })).length > 0;
}
