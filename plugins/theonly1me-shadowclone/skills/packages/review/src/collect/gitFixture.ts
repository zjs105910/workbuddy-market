import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export type GitFixture = {
  readonly directory: string;
  readonly write: (files: Readonly<Record<string, string>>) => Promise<void>;
  readonly commit: (message: string) => string;
};

function git(options: { readonly directory: string; readonly arguments: readonly string[] }): string {
  const result = Bun.spawnSync(
    ["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "-c", "commit.gpgsign=false", ...options.arguments],
    { cwd: options.directory, env: { PATH: process.env.PATH ?? "", HOME: options.directory, GIT_CONFIG_NOSYSTEM: "1" } },
  );

  if (result.exitCode !== 0) {
    throw new Error(result.stderr.toString());
  }

  return result.stdout.toString().trim();
}

export async function createGitFixture(): Promise<GitFixture> {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-review-test-"));

  git({ directory, arguments: ["init", "--quiet", "--initial-branch=main"] });

  return {
    directory,
    write: async (files) => {
      for (const [filePath, content] of Object.entries(files)) {
        await Bun.write(path.join(directory, filePath), content);
      }
    },
    commit: (message) => {
      git({ directory, arguments: ["add", "--all"] });
      git({ directory, arguments: ["commit", "--quiet", "--message", message] });

      return git({ directory, arguments: ["rev-parse", "HEAD"] });
    },
  };
}
