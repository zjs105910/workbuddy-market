import { readEnvironment, readHarnessManifest } from "@shadowclone/environment";
import { readEffectiveConfig, projectPaths, type ProjectPaths } from "@shadowclone/core";
import {
  memoryCandidates,
  memoryTitle,
  recordMemoryDecision,
  repositoryRoot,
} from "@shadowclone/harness";
import {
  isOriginBlocked,
  resolveRepository,
  type GitRemoteReader,
} from "@shadowclone/sessions";
import { promptConfirmation, type ConfirmPrompt } from "./confirm";
import { harnessInitCommand } from "./harness";

async function promoteMemoryNotes(options: {
  readonly root: string;
  readonly apply: boolean;
  readonly paths: ProjectPaths;
  readonly managedConfigPath: string | null;
  readonly readRemote?: GitRemoteReader;
  readonly ask: ConfirmPrompt;
  readonly writeLine: (line: string) => void;
}): Promise<void> {
  const { config, policy } = await readEffectiveConfig({
    configPath: options.paths.configFile,
    managedConfigPath: options.managedConfigPath,
  });

  if (!config.sources["claude-memory"]) {
    options.writeLine(
      "Claude memory is not read. Enable the claude-memory source to turn its feedback notes into repository rules.",
    );

    return;
  }

  const repository = await resolveRepository({
    cwd: options.root,
    enabled: config.sources["git-metadata"],
    readRemote: options.readRemote,
  });

  if (isOriginBlocked({ repository, patterns: policy.blockedOrigins })) {
    throw new Error("Managed policy blocks this repository");
  }

  const candidates = await memoryCandidates({
    paths: options.paths,
    root: options.root,
    repository,
  });

  if (!options.apply) {
    if (candidates.length > 0) {
      options.writeLine(
        `${candidates.length} Claude memory note(s) can become repository rules. Run \`shadowclone sync\` to review them one at a time.`,
      );
    }

    return;
  }

  for (const file of candidates) {
    options.writeLine(`Claude memory (${file.kind}): ${memoryTitle(file)}`);

    const promote = await options.ask(
      "Add this note to this repository's rules? It will appear in the committed AGENTS.md.",
    );

    await recordMemoryDecision({
      paths: options.paths,
      repository,
      file,
      promote,
    });
  }
}

export async function harnessSyncCommand(options: {
  readonly apply: boolean | "confirm";
  readonly cwd?: string;
  readonly paths?: ProjectPaths;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
  readonly ask?: ConfirmPrompt;
  readonly writeLine?: (line: string) => void;
}): Promise<string | null> {
  const paths = options.paths ?? projectPaths;
  const managedConfigPath =
    options.managedConfigPath === undefined
      ? paths.managedConfigFile
      : options.managedConfigPath;
  const ask = options.ask ?? promptConfirmation;
  const writeLine = options.writeLine ?? console.log;

  const root = await repositoryRoot({ cwd: options.cwd ?? process.cwd() });
  const manifest = await readHarnessManifest(root);

  if ((await readEnvironment(paths)) === null) {
    await promoteMemoryNotes({
      root,
      apply: options.apply !== false,
      paths,
      managedConfigPath,
      readRemote: options.readRemote,
      ask,
      writeLine,
    });
  }

  if (manifest === null) {
    return null;
  }

  return harnessInitCommand({
    apply: options.apply,
    personal: null,
    skills: [],
    enforceClaude: false,
    cwd: root,
    paths,
    managedConfigPath,
    readRemote: options.readRemote,
    ask,
    writeLine,
  });
}
