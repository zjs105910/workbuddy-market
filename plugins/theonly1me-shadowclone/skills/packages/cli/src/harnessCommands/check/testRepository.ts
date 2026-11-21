import { symlink } from "node:fs/promises";
import path from "node:path";
import { checkoutRoot } from "@shadowclone/core/testing";
import { harnessInitCommand } from "../../harness";
import {
  acceptAll,
  bunTaskList,
  harnessTestSetup,
  type HarnessTestSetup,
} from "@shadowclone/harness/testing";

export const checkedRules = [
  "## File size\n\nKeep every file under 200 lines.\n",
  "## Comments\n\nWrite zero comments in TypeScript files.\n",
  "## Prose\n\nNo em-dashes anywhere.\n",
  "## Suppressions\n\nNever silence a lint or type rule with a suppression.\n",
].join("\n");

export function git(options: {
  readonly root: string;
  readonly arguments: readonly string[];
}): void {
  const result = Bun.spawnSync(
    [
      "git",
      "-c",
      "user.name=Harness Test",
      "-c",
      "user.email=harness@example.com",
      "-c",
      "commit.gpgsign=false",
      "-c",
      "core.hooksPath=/dev/null",
      ...options.arguments,
    ],
    {
      cwd: options.root,
      env: {
        ...process.env,
        GIT_CONFIG_GLOBAL: "/dev/null",
        GIT_CONFIG_NOSYSTEM: "1",
      },
    },
  );

  if (result.exitCode !== 0) {
    throw new Error(`git ${options.arguments[0]} failed`);
  }
}

export async function checkedRepository(
  options: { readonly enforceClaude?: boolean } = {},
): Promise<HarnessTestSetup> {
  const setup = await harnessTestSetup({
    fixture: bunTaskList,
    globalRules: checkedRules,
  });

  await harnessInitCommand({
    apply: true,
    personal: true,
    skills: [],
    enforceClaude: options.enforceClaude ?? false,
    cwd: setup.root,
    paths: setup.paths,
    managedConfigPath: null,
    ask: acceptAll,
    writeLine: () => undefined,
  });
  await Bun.write(path.join(setup.root, ".gitignore"), "node_modules\n");
  await symlink(
    path.join(await checkoutRoot(), "node_modules"),
    path.join(setup.root, "node_modules"),
  );
  git({ root: setup.root, arguments: ["init", "-q"] });
  git({ root: setup.root, arguments: ["add", "-A"] });
  git({ root: setup.root, arguments: ["commit", "-q", "-m", "initial"] });

  return setup;
}
