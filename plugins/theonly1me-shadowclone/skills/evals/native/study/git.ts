import path from "node:path";
import { runProcess } from "@shadowclone/core";
import { writeFrozenFile } from "../files";
import type { GitHistory } from "./schema";

const identity = {
  GIT_AUTHOR_NAME: "Tally Developer",
  GIT_AUTHOR_EMAIL: "developer@tally.example",
  GIT_COMMITTER_NAME: "Tally Developer",
  GIT_COMMITTER_EMAIL: "developer@tally.example",
  GIT_CONFIG_NOSYSTEM: "1",
  GIT_CONFIG_GLOBAL: "/dev/null",
};

export type GitCommit = {
  readonly hash: string;
  readonly subject: string;
  readonly body: string;
  readonly trailers: string;
};

export type GitState = {
  readonly branch: string;
  readonly head: string;
  readonly refs: readonly string[];
  readonly commits: readonly GitCommit[];
};

export async function git(options: { directory: string; arguments: readonly string[]; date?: number }): Promise<string> {
  const date = options.date === undefined ? {} : {
    GIT_AUTHOR_DATE: new Date(options.date).toISOString(), GIT_COMMITTER_DATE: new Date(options.date).toISOString(),
  };
  const result = await runProcess({
    arguments: ["git", ...options.arguments], cwd: options.directory,
    environment: { PATH: process.env.PATH, HOME: options.directory, ...identity, ...date },
    timeoutMilliseconds: 30_000, maximumOutputBytes: 4_000_000,
  });

  if (result.exitCode !== 0) {
    throw new Error(`Git fixture command failed: ${options.arguments.slice(0, 2).join(" ")}`);
  }

  return result.stdout;
}

export async function buildGitHistory(options: {
  readonly directory: string;
  readonly origin: string;
  readonly history: GitHistory;
}): Promise<readonly string[]> {
  const { directory, history } = options;
  let date = Date.UTC(2026, 8, 1, 9);
  const commit = async (message: string) => {
    date += 3_600_000;
    await git({ directory, arguments: ["add", "-A"] });
    await git({ directory, arguments: ["commit", "--quiet", "--no-verify", "-m", message], date });
  };

  await git({ directory, arguments: ["init", "--quiet", "-b", "main"] });
  await git({ directory, arguments: ["config", "user.name", identity.GIT_AUTHOR_NAME] });
  await git({ directory, arguments: ["config", "user.email", identity.GIT_AUTHOR_EMAIL] });
  await git({ directory, arguments: ["config", "commit.gpgsign", "false"] });
  await commit("chore: import tally");

  for (const branch of history.branches) {
    if (branch.name !== "main") {
      await git({ directory, arguments: ["checkout", "--quiet", "-b", branch.name, branch.from ?? "main"] });
    }

    for (const entry of branch.commits) {
      for (const file of entry.files) {
        await writeFrozenFile({ directory, file });
      }

      await commit(entry.message);
    }
  }

  await git({ directory: path.dirname(options.origin), arguments: ["init", "--quiet", "--bare", options.origin] });
  await git({ directory, arguments: ["remote", "add", "origin", options.origin] });

  if (history.pushed) {
    await git({ directory, arguments: ["push", "--quiet", "--all", "-u", "origin"] });
  }

  await git({ directory, arguments: ["checkout", "--quiet", history.checkout] });
  return (await git({ directory, arguments: ["rev-list", "--all"] })).split("\n").filter(Boolean);
}

export async function readGitState(options: {
  readonly directory: string;
  readonly initialCommits: readonly string[];
}): Promise<GitState> {
  const { directory } = options;
  const branch = (await git({ directory, arguments: ["rev-parse", "--abbrev-ref", "HEAD"] })).trim();
  const head = (await git({ directory, arguments: ["rev-parse", "HEAD"] })).trim();
  const refs = (await git({ directory, arguments: ["for-each-ref", "--format=%(refname) %(objectname)"] })).split("\n").filter(Boolean);
  const known = new Set(options.initialCommits);
  const log = await git({ directory, arguments: ["log", "--all", "--format=%H%x1f%s%x1f%b%x1f%(trailers:only)%x1e"] });
  const commits = log.split("\x1e").map((entry) => entry.trim()).filter(Boolean).map((entry) => {
    const [hash = "", subject = "", body = "", trailers = ""] = entry.split("\x1f");
    return { hash, subject, body: body.trim(), trailers: trailers.trim() };
  }).filter((entry) => !known.has(entry.hash));
  return { branch, head, refs, commits };
}
