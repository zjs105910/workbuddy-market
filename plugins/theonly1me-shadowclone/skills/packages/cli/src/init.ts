import { initialConfiguration } from "./initConfiguration";
import { prepareInitialEnvironment } from "./initEnvironment";
import {
  applyManagedPolicy,
  readManagedPolicy,
  writeConfig,
  projectPaths,
  type ProjectPaths,
} from "@shadowclone/core";
import type { ManagedPolicy } from "@shadowclone/core";
import type { EngineId, EngineRunner } from "@shadowclone/agents";
import {
  type IntegrationAgent,
  pendingLearningRecords,
  readEnvironment,
} from "@shadowclone/environment";
import {
  initializeAdvanced,
  type ConsentPrompt,
  type InitializeAdvancedOptions,
} from "./initAdvanced";
import {
  detectPersonalSkills,
  detectedAgentNames,
  detectedIntegrationAgents,
  printDetectionSummary,
} from "./initDetection";
import { createSetupEngine, runSetupLearning } from "./initLearning";
import { installNativeCommand } from "./native";
import { describeSkippedAgent, type SkippedAgent } from "./skippedAgents";
import { maintainSkills } from "@shadowclone/learning";
import {
  detectOnboardingPresence,
  type OnboardingPresence,
} from "./onboardingPresence";
import type { InitializeConsent } from "./initOptions";
import { chooseLearningModel } from "./initModels";

export type { ConsentPrompt } from "./initAdvanced";

export function answerIsYes(answer: string | null): boolean {
  if (answer === null) {
    return false;
  }

  const normalized = answer.trim().toLowerCase();

  return normalized === "" || normalized === "y" || normalized === "yes";
}

function promptForConsent(question: string): boolean {
  return answerIsYes(prompt(question));
}

export type InitializeOptions = InitializeAdvancedOptions & {
  readonly advanced?: boolean;
  readonly agents?: readonly IntegrationAgent[];
  readonly install?: typeof installNativeCommand;
  readonly runner?: EngineRunner;
  readonly engine?: EngineId;
  readonly now?: number;
  readonly consent?: InitializeConsent;
};

export async function initialize(
  options: InitializeOptions = {},
): Promise<void> {
  if (options.advanced) {
    await initializeAdvanced(options);

    return;
  }

  const paths: ProjectPaths = options.paths ?? projectPaths;
  const workingDirectory = options.workingDirectory ?? process.cwd();
  const configPath = options.configPath ?? paths.configFile;

  const presence: OnboardingPresence =
    options.presence ??
    (await detectOnboardingPresence({
      paths,
      workingDirectory,
    }));
  const agents = options.agents ?? (await detectedIntegrationAgents(paths));
  const personalSkillsPresent = await detectPersonalSkills(paths);

  const ask: ConsentPrompt = options.ask ?? promptForConsent;
  const writeLine = options.writeLine ?? console.log;
  const policy: ManagedPolicy =
    options.managedPolicy ??
    (await readManagedPolicy(
      options.managedConfigPath === undefined
        ? paths.managedConfigFile
        : options.managedConfigPath,
    ));

  printDetectionSummary({
    paths,
    presence,
    agents,
    personalSkillsPresent,
    writeLine,
  });

  const learn =
    options.consent?.learn ??
    (await ask("Learn how you work from these sessions? [Y/n]"));
  const skillPrompt =
    agents.length > 0
      ? `Keep your skills in sync and automatically maintain them across ${detectedAgentNames(agents)}? [Y/n]`
      : "Keep your skills in sync and automatically maintain them across your agents? [Y/n]";
  const skills = options.consent?.skills ?? (await ask(skillPrompt));
  const background =
    options.consent?.background ??
    (await ask("Keep improving in the background as you work? [Y/n]"));

  if (background && !learn) {
    throw new Error("Background learning requires session learning");
  }

  const initial = initialConfiguration({ learn, skills, background, presence });
  const selection = learn && agents.includes("pi") && options.consent === undefined && !options.runner
    ? await chooseLearningModel({ paths, answer: options.answer, writeLine }) : null;
  const config = { ...initial, distillation: { ...initial.distillation,
    ...(selection ? { engine: selection.engine, model: selection.model } : {}) } };

  await writeConfig({ config, configPath });

  const environment = await prepareInitialEnvironment({
    ...options,
    paths,
    workingDirectory,
    policy,
    learn,
    skills,
    presence,
    writeLine,
  });
  let rulesLearned = environment.rulesLearned;
  const skillsSynced = environment.skillsSynced;

  const deepAllowed =
    learn && policy.enabled && policy.distillation === "allowed";
  const setupEngine = deepAllowed
    ? await createSetupEngine({
        policy,
        engine: options.engine,
        runner: options.runner,
        preferences: config.distillation,
      })
    : null;

  if (deepAllowed && learn && setupEngine) {
    try {
      rulesLearned += await runSetupLearning({
        paths,
        configPath,
        config: applyManagedPolicy({ config, policy }),
        policy,
        setupEngine,
        now: options.now ?? Date.now(),
        readRemote: options.readRemote,
        writeLine,
        ...(options.consent === undefined ? { confirmHistoricalRepository: ask } : {}),
      });
    } catch (error) {
      if (!(error instanceof Error)) {
        throw error;
      }

      if (error.message === "Learning deadline reached") {
        writeLine(
          background ? "Learning reached its time budget; background learning will continue."
            : "Learning reached its time budget. Run shadowclone learn --deep to continue.",
        );
      } else if (
        error.message === "Learning call limit reached" ||
        error.message === "Learning cost limit reached"
      ) {
        writeLine(
          background ? "Learning reached its setup budget; background learning will continue."
            : "Learning reached its setup budget. Run shadowclone learn --deep to continue.",
        );
      } else {
        throw error;
      }
    }
  } else if (deepAllowed) {
    writeLine(
      "No authenticated agent CLI is available for the first learning pass.",
    );
  }

  if (skills && setupEngine && rulesLearned > environment.rulesLearned) {
    const publication = await maintainSkills({
      paths,
      execution: setupEngine.execution,
      managedConfigPath: options.managedConfigPath,
      readRemote: options.readRemote,
    });

    if (publication.pending + publication.deferred + publication.conflicts > 0) {
      writeLine(`${publication.pending + publication.deferred + publication.conflicts} learned guidance item(s) still need scope or publication review.`);
    }
  }

  let skippedAgents: readonly SkippedAgent[] = [];

  if (agents.length > 0) {
    ({ skipped: skippedAgents } = await (options.install ?? installNativeCommand)({
      agents,
      scope: "global",
      subagent: false,
      autoDelegate: false,
      skipUnsafeDestinations: true,
    }));
  }

  const state = await readEnvironment(paths);
  const active = new Set(state?.dispositions.filter((entry) =>
    entry.status === "published" || entry.status === "covered"
  ).map((entry) => entry.key) ?? []);
  const pending = state === null ? 0 : pendingLearningRecords({ paths, state }).length;

  writeLine(`${skillsSynced} skills synced; ${rulesLearned} rules learned; ${active.size} active; ${pending} awaiting scope or publication; ${agents.length - skippedAgents.length} agents installed.`);
  writeLine("Start a new agent session to load active guidance. Review pending items with shadowclone learning pending.");

  for (const skipped of skippedAgents) {
    writeLine(describeSkippedAgent(skipped));
  }
}
