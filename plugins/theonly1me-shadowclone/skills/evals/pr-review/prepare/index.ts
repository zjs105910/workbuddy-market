import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { git } from "../git";
import { type UpstreamPull, upstreamPullSchema } from "../mine/pulls";
import { evalCaseSchema, type SelectedCase, selectedCaseSchema } from "../sample";

export const preparedCaseSchema = evalCaseSchema.extend({ checkout: z.string(), branchHeadSha: z.string() });

export type PreparedCase = z.infer<typeof preparedCaseSchema>;

export const caseRepositoryName = "vite";

async function caseCheckout(options: { readonly clone: string; readonly directory: string; readonly baseSha: string; readonly headSha: string }): Promise<void> {
  const { directory } = options;

  rmSync(directory, { recursive: true, force: true });
  mkdirSync(directory, { recursive: true });
  await git({ clone: directory, arguments: ["init", "--quiet", "--initial-branch=main"] });
  writeFileSync(path.join(directory, ".git", "objects", "info", "alternates"), `${path.join(options.clone, ".git", "objects")}\n`);
  await git({ clone: directory, arguments: ["update-ref", "refs/heads/main", options.baseSha] });
  await git({ clone: directory, arguments: ["update-ref", "refs/heads/case", options.headSha] });
  await git({ clone: directory, arguments: ["symbolic-ref", "HEAD", "refs/heads/case"] });
  await git({ clone: directory, arguments: ["reset", "--hard", "--quiet"] });
}

async function prepareCase(options: {
  readonly entry: SelectedCase;
  readonly upstream: UpstreamPull;
  readonly clone: string;
  readonly casesDirectory: string;
}): Promise<PreparedCase> {
  const { entry, clone } = options;
  const pullRef = `refs/upstream-pulls/${entry.upstream}`;

  if ((await git({ clone, arguments: ["rev-parse", "--quiet", "--verify", pullRef] }).catch(() => "")) === "") {
    await git({ clone, arguments: ["fetch", "--quiet", "origin", `+refs/pull/${entry.upstream}/head:${pullRef}`] });
  }

  const headSha = await git({ clone, arguments: ["rev-parse", pullRef] });
  const baseSha = await git({ clone, arguments: ["merge-base", options.upstream.base.sha, headSha] });
  const message = `${options.upstream.title}\n\n${options.upstream.body ?? ""}`.trim();
  const branchHeadSha = await git({ clone, arguments: ["commit-tree", "-S", `${headSha}^{tree}`, "-p", baseSha, "-m", message] });
  const checkout = path.join(options.casesDirectory, entry.id, caseRepositoryName);

  await caseCheckout({ clone, directory: checkout, baseSha, headSha: branchHeadSha });

  return { ...entry, baseSha, headSha, checkout, branchHeadSha };
}

export async function prepareCases(options: { readonly mined: string; readonly clone: string; readonly casesDirectory: string }): Promise<readonly PreparedCase[]> {
  const selected = z.array(selectedCaseSchema).parse(JSON.parse(readFileSync(path.join(options.mined, "selected.json"), "utf8")));
  const pulls = new Map(z.array(upstreamPullSchema).parse(JSON.parse(readFileSync(path.join(options.mined, "pulls.json"), "utf8"))).map((pull) => [pull.number, pull]));
  const prepared: PreparedCase[] = [];

  for (const entry of selected) {
    const upstream = pulls.get(entry.upstream);

    if (upstream === undefined) {
      throw new Error(`pulls.json has no upstream pull request ${entry.upstream}`);
    }

    prepared.push(await prepareCase({ entry, upstream, clone: options.clone, casesDirectory: options.casesDirectory }));
    console.error(`prepared ${entry.id} from upstream ${entry.upstream}`);
  }

  writeFileSync(path.join(options.mined, "prepared.json"), JSON.stringify(prepared, null, 2));
  return prepared;
}

export function readPreparedCases(mined: string): readonly PreparedCase[] {
  return z.array(preparedCaseSchema).parse(JSON.parse(readFileSync(path.join(mined, "prepared.json"), "utf8")));
}
