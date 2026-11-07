import {
  defaultConfig,
  readManagedPolicy,
  setDeepEnabled,
  setSourceEnabled,
  writeConfig,
  type ProjectPaths,
  projectPaths,
  repairOwnedTree,
} from "@shadowclone/core";
import type { ManagedPolicy } from "@shadowclone/core";
import { importRepositoryGuidance } from "@shadowclone/learning";
import type { GitRemoteReader } from "@shadowclone/sessions";
import type { SeedLibrary } from "@shadowclone/skills";
import {
  detectOnboardingPresence,
  type OnboardingCaptureSourceId,
  type OnboardingPresence,
} from "./onboardingPresence";
import type { WizardAnswerPrompt } from "./wizard";
import { offerInitialGuidance } from "./initGuidance";
import { initializeSkillEnvironment } from "@shadowclone/environment";

export type ConsentPrompt = (question: string) => boolean | Promise<boolean>;

const captureSources: readonly {
  readonly id: OnboardingCaptureSourceId;
  readonly question: string;
}[] = [
  { id: "antigravity", question: "Enable Antigravity CLI transcripts?" },
  { id: "claude-code", question: "Enable Claude Code transcripts?" },
  { id: "claude-prompts", question: "Enable Claude prompt history?" },
  { id: "codex", question: "Enable Codex transcripts?" },
  { id: "cursor", question: "Enable Cursor CLI chat stores?" },
  { id: "pi", question: "Enable Pi transcripts?" },
];

function promptForConsent(question: string): boolean {
  const answer = prompt(`${question} [y/N]`);

  return answer?.trim().toLowerCase() === "y";
}

export type InitializeAdvancedOptions = {
  readonly configPath?: string;
  readonly paths?: ProjectPaths;
  readonly workingDirectory?: string;
  readonly presence?: OnboardingPresence;
  readonly library?: SeedLibrary;
  readonly answer?: WizardAnswerPrompt;
  readonly ask?: ConsentPrompt;
  readonly writeLine?: (line: string) => void;
  readonly managedConfigPath?: string | null;
  readonly managedPolicy?: ManagedPolicy;
  readonly readRemote?: GitRemoteReader;
};

export async function initializeAdvanced(
  options: InitializeAdvancedOptions = {},
): Promise<void> {
  const paths = options.paths ?? projectPaths;
  const configPath = options.configPath ?? paths.configFile;

  const presence =
    options.presence ??
    (await detectOnboardingPresence({
      paths,
      workingDirectory: options.workingDirectory ?? process.cwd(),
    }));

  const ask = options.ask ?? promptForConsent;
  const writeLine = options.writeLine ?? ((line) => console.log(line));
  const policy =
    options.managedPolicy ??
    (await readManagedPolicy(
      options.managedConfigPath === undefined
        ? paths.managedConfigFile
        : options.managedConfigPath,
    ));

  const importEnabled = await offerInitialGuidance({
    ...options,
    policy,
    paths,
    presence,
    ask,
    writeLine,
  });

  let config = defaultConfig;
  let captureEnabled = false;

  for (const source of captureSources) {
    if (!presence.presentCaptureSources.has(source.id)) {
      continue;
    }

    const enabled = await ask(source.question);

    config = setSourceEnabled({ config, source: source.id, enabled });
    captureEnabled = captureEnabled || enabled;
  }

  const enableGitMetadata = await ask(
    "Enable reading git remote origins for organization-scoped profiles?",
  );
  const enableAgentContext = await ask(
    "Enable reading existing agent instructions, skills and native memory?",
  );
  const enableClaudeMemory = await ask(
    "Enable read-only extraction from Claude memory for explicitly registered repositories?",
  );
  const enableAntigravityWorkspaces = await ask(
    "Enable Antigravity workspace-history metadata for repository attribution?",
  );
  const enableDeep = await ask(
    "Allow deep learning to send redacted correction evidence and profile guidance through your authenticated agent CLI?",
  );

  config = setSourceEnabled({
    config,
    source: "declared-rules",
    enabled: importEnabled,
  });
  config = setSourceEnabled({
    config,
    source: "git-metadata",
    enabled: enableGitMetadata,
  });
  config = setSourceEnabled({
    config,
    source: "agent-context",
    enabled: enableAgentContext,
  });
  config = setSourceEnabled({
    config,
    source: "claude-memory",
    enabled: enableClaudeMemory,
  });
  config = setSourceEnabled({
    config,
    source: "antigravity-workspaces",
    enabled: enableAntigravityWorkspaces,
  });
  config = setDeepEnabled({ config, enabled: enableDeep });

  if (enableDeep && policy.enabled && policy.distillation === "allowed") {
    const automatic = await ask(
      "Allow bounded automatic learning and profile updates at session boundaries? User-authored guidance remains protected.",
    );

    config = { ...config, distillation: { ...config.distillation, automatic } };
  }

  await writeConfig({ config, configPath });

  if (policy.enabled) {
    await initializeSkillEnvironment({ paths, automatic: false });
  }

  await repairOwnedTree(paths.shadowcloneDirectory);

  if (importEnabled) {
    const imported = await importRepositoryGuidance({
      paths,
      workingDirectory: options.workingDirectory ?? process.cwd(),
      gitMetadataEnabled:
        config.sources["git-metadata"] &&
        policy.allowedSources.includes("git-metadata"),
      blockedOrigins: policy.blockedOrigins,
      readRemote: options.readRemote,
    });

    writeLine(
      `Imported ${imported.imported} repository guidance files; ${imported.preserved} preserved; ${imported.rejected} rejected; ${imported.retired} retired.`,
    );
  }

  writeLine(
    captureEnabled ||
      importEnabled ||
      enableGitMetadata ||
      enableAgentContext ||
      enableClaudeMemory ||
      enableAntigravityWorkspaces ||
      enableDeep
      ? "Selected sources and capabilities enabled."
      : "All capture sources remain disabled.",
  );

  if (captureEnabled) {
    writeLine(
      "Run shadowclone learn to build evidence from the sources you enabled.",
    );
  }
}
