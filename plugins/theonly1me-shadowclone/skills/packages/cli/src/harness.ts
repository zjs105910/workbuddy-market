import {
  readConfig,
  readManagedPolicy,
  setSourceEnabled,
  writeConfig,
  canonicalPath,
  projectPaths,
  type ProjectPaths,
} from "@shadowclone/core";
import { readHarnessManifest } from "@shadowclone/environment";
import {
  applyHarness,
  planHarness,
  renderHarnessOutcome,
  renderHarnessPreview,
} from "@shadowclone/harness";
import type { GitRemoteReader } from "@shadowclone/sessions";
import { promptConfirmation, type ConfirmPrompt } from "./confirm";

export type RepositoryInitOptions = {
  readonly personal: boolean | null;
  readonly skills: readonly string[];
  readonly enforceClaude: boolean;
};

export type HarnessInitOptions = RepositoryInitOptions & {
  readonly apply: boolean | "confirm";
};

export function parseRepositoryInit(
  arguments_: readonly string[],
): RepositoryInitOptions | null {
  let personal: boolean | null = null;
  let enforceClaude = true;
  const skills: string[] = [];

  for (let position = 0; position < arguments_.length; position += 1) {
    const argument = arguments_[position];

    if (argument === "--personal" && personal === null) {
      personal = true;
    } else if (argument === "--no-personal" && personal === null) {
      personal = false;
    } else if (argument === "--skill" && arguments_[position + 1]) {
      skills.push(arguments_[++position] ?? "");
    } else if (argument === "--no-enforce") {
      enforceClaude = false;
    } else {
      return null;
    }
  }

  return { personal, skills, enforceClaude };
}

const manifestQuestion =
  "Repository setup reads this repository's package.json scripts and dependency names, lockfile names, pyproject.toml, requirements.txt, Makefile targets, CI workflow files, and top-level entry names. Allow reading them?";
const personalQuestion =
  "Include your personal global preferences in this repository's AGENTS.md? They will be committed and visible to anyone with repository access.";

export async function harnessInitCommand(
  options: HarnessInitOptions & {
    readonly cwd?: string;
    readonly paths?: ProjectPaths;
    readonly managedConfigPath?: string | null;
    readonly readRemote?: GitRemoteReader;
    readonly ask?: ConfirmPrompt;
    readonly writeLine?: (line: string) => void;
  },
): Promise<string | null> {
  const paths = options.paths ?? projectPaths;
  const ask = options.ask ?? promptConfirmation;
  const writeLine = options.writeLine ?? console.log;
  const managedConfigPath =
    options.managedConfigPath === undefined
      ? paths.managedConfigFile
      : options.managedConfigPath;

  const policy = await readManagedPolicy(managedConfigPath);

  if (!policy.enabled) {
    throw new Error("Shadowclone is disabled by managed policy");
  }

  if (!policy.allowedSources.includes("repository-manifests")) {
    throw new Error("Managed policy blocks reading repository manifests");
  }

  let config = await readConfig({ configPath: paths.configFile });

  if (!config.sources["repository-manifests"]) {
    if (!(await ask(manifestQuestion))) {
      writeLine("Nothing was read or written.");

      return null;
    }

    config = setSourceEnabled({
      config,
      source: "repository-manifests",
      enabled: true,
    });
    await writeConfig({ config, configPath: paths.configFile });
  }

  if (
    options.skills.length > 0 &&
    !(
      config.sources["skill-library"] &&
      policy.allowedSources.includes("skill-library")
    )
  ) {
    throw new Error(
      "Copying personal skills needs the skill-library source; run `shadowclone skills configure` first",
    );
  }

  const root = canonicalPath(options.cwd ?? process.cwd());
  const personal =
    options.personal ??
    (await readHarnessManifest(root))?.personal ??
    (await ask(personalQuestion));
  const plan = await planHarness({
    root,
    personal,
    skillNames: options.skills,
    enforceClaude: options.enforceClaude,
    paths,
    managedConfigPath,
    readRemote: options.readRemote,
  });

  writeLine(renderHarnessPreview({ plan }).trimEnd());

  const writes = plan.files.some(
    (file) => file.status === "create" || file.status === "update",
  );
  const approved =
    options.apply === true ||
    (options.apply === "confirm" &&
      writes &&
      (await ask("Write these repository files?")));
  const revision = approved
    ? await applyHarness({ paths, plan })
    : writes
      ? undefined
      : null;

  writeLine(renderHarnessOutcome(revision));

  return revision ?? null;
}
