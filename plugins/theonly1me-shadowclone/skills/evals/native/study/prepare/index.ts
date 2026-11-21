import { lstat, mkdir } from "node:fs/promises";
import path from "node:path";
import { z } from "zod";
import type { NativeEngineRunner } from "@shadowclone/agents";
import { readEnvironment } from "@shadowclone/environment";
import { createProjectPaths, type ProjectPaths, ownedWrite } from "@shadowclone/core";
import { readGitRemote } from "@shadowclone/sessions";
import { evaluationBudget } from "../../../shared/accounting";
import { lockEvaluation } from "../../../shared/lock";
import { requirePrivateDirectory } from "../../files";
import { copyWorkspace } from "../../workspace";
import { authorizeStudy } from "../authorize";
import { prepareDeep } from "./deep";
import { prepareFirstTime } from "./firstTime";
import { captureArm } from "./freeze";
import { createLearningRunner } from "./learningRunner";
import { copyPersonalLibrary } from "./library";
import { migrateLegacyProfile } from "./migrate";
import { applyPendingChanges } from "./resolve";
import { activateWithResolution } from "./activate";
import { installClaudeRouting } from "./claude";

export const preparationSchema = z.strictObject({
  studyDirectory: z.string().min(1),
  sourceHome: z.string().min(1),
  transcriptRoot: z.string().min(1),
  templateDirectory: z.string().min(1),
  remote: z.string().min(1).nullable(),
  wizardBuild: z.array(z.string().min(1)).min(1),
  cliVersion: z.string().min(1),
  maximumCalls: z.number().int().min(1).max(400),
  maximumPasses: z.number().int().min(1).max(6),
  callsPerPass: z.number().int().min(2).max(40),
  deadlineAt: z.number().positive(),
  legacyProfileDirectory: z.string().min(1).nullable().default(null),
});

export const preparationStages = ["original", "first-time", "deep", "deep-continue", "resolve", "activate", "freeze", "claude", "freeze-claude"] as const;
export type PreparationStage = (typeof preparationStages)[number];
export type Preparation = z.infer<typeof preparationSchema>;

async function requireAbsent(directory: string): Promise<void> {
  if (await lstat(directory).catch(() => null)) {
    throw new Error("Preparation stage already ran; start a new study directory");
  }
}

async function assertConfined(options: { paths: ProjectPaths; directory: string }): Promise<void> {
  const state = await readEnvironment(options.paths);
  const outside = (state?.repositories ?? []).filter((repository) => !repository.directory.startsWith(`${options.directory}${path.sep}`));

  if (outside.length > 0) {
    throw new Error("A registered repository is outside the study directory; stop before publishing");
  }
}

export function preparationLayout(studyDirectory: string) {
  const home = (arm: string) => path.join(studyDirectory, "homes", arm);
  const workspace = (arm: string) => path.join(studyDirectory, "workspaces", arm);
  return { home, workspace, arms: path.join(studyDirectory, "arms.json"), armsClaude: path.join(studyDirectory, "arms.claude.json"), log: path.join(studyDirectory, "preparation-log.json") };
}

export async function runPreparation(options: {
  readonly preparation: Preparation;
  readonly stage: PreparationStage;
  readonly nativeRunner?: NativeEngineRunner;
  readonly writeLine?: (line: string) => void;
}): Promise<unknown> {
  const { preparation } = options;
  await authorizeStudy();
  await requirePrivateDirectory(process.cwd()).catch(() => {
    throw new Error("Run study preparation from a directory outside every repository");
  });
  const directory = await requirePrivateDirectory(preparation.studyDirectory);
  await mkdir(directory, { recursive: true, mode: 0o700 });
  const release = await lockEvaluation(directory);
  const layout = preparationLayout(directory);
  const writeLine = options.writeLine ?? console.log;
  const readRemote = async (cwd: string) => cwd.startsWith(path.join(directory, "workspaces")) ? preparation.remote : readGitRemote(cwd);

  try {
    const budget = await evaluationBudget({
      directory, resume: await Bun.file(path.join(directory, "budget.json")).exists(), maximumCalls: preparation.maximumCalls,
    });
    const runner = (label: string) => createLearningRunner({
      directory, budget, label, cliVersion: preparation.cliVersion, deadlineAt: preparation.deadlineAt,
      blockedPaths: [preparation.templateDirectory, path.join(directory, "arms.json")],
      ...(options.nativeRunner ? { nativeRunner: options.nativeRunner } : {}),
    });
    const paths = (arm: string) => createProjectPaths({ homeDirectory: layout.home(arm), platform: process.platform });
    const learningPaths = (arm: string) => ({ ...paths(arm), claudeProjectsDirectory: preparation.transcriptRoot });

    if (options.stage === "original") {
      await requireAbsent(layout.home("original"));
      await mkdir(layout.home("original"), { recursive: true, mode: 0o700 });
      await copyWorkspace({ source: preparation.templateDirectory, target: layout.workspace("original") });
      return await copyPersonalLibrary({ sourceHome: preparation.sourceHome, targetHome: layout.home("original") });
    }

    if (options.stage === "first-time") {
      await requireAbsent(layout.home("first-time"));
      await copyWorkspace({ source: layout.home("original"), target: layout.home("first-time") });
      await copyWorkspace({ source: preparation.templateDirectory, target: layout.workspace("first-time") });
      return await prepareFirstTime({
        paths: paths("first-time"), learningPaths: learningPaths("first-time"), workspace: layout.workspace("first-time"),
        runner: runner("first-time"), readRemote, build: preparation.wizardBuild, writeLine,
      });
    }

    if (options.stage === "deep" || options.stage === "deep-continue") {
      if (options.stage === "deep") {
        await requireAbsent(layout.home("deep"));
        await copyWorkspace({ source: layout.home("original"), target: layout.home("deep") });
        await copyWorkspace({ source: preparation.templateDirectory, target: layout.workspace("deep") });
        if (preparation.legacyProfileDirectory) {
          const migrated = await migrateLegacyProfile({
            paths: paths("deep"), sourceProfileDirectory: preparation.legacyProfileDirectory, workspace: layout.workspace("deep"),
            runner: runner("deep"), readRemote, passes: 3, writeLine,
          });
          await ownedWrite({ path: path.join(directory, "deep-migration.json"), content: JSON.stringify(migrated, null, 2) });
        }
        await prepareFirstTime({
          paths: paths("deep"), learningPaths: learningPaths("deep"), workspace: layout.workspace("deep"),
          runner: runner("deep"), readRemote, build: preparation.wizardBuild, writeLine,
        });
      }
      const passes = await prepareDeep({
        learningPaths: learningPaths("deep"), workspace: layout.workspace("deep"), runner: runner("deep"), readRemote,
        maximumPasses: preparation.maximumPasses, callsPerPass: preparation.callsPerPass, writeLine,
      });
      await ownedWrite({ path: path.join(directory, `${options.stage}-passes.json`), content: JSON.stringify(passes, null, 2) });
      await assertConfined({ paths: paths("deep"), directory });
      return passes;
    }

    if (options.stage === "resolve") {
      return await applyPendingChanges({ paths: paths("deep"), directory });
    }

    if (options.stage === "activate") {
      const activated = await activateWithResolution(paths("deep"));
      await assertConfined({ paths: paths("deep"), directory });
      return activated;
    }

    if (options.stage === "claude") {
      const installed = [];
      for (const arm of ["first-time", "deep"] as const) {
        installed.push(await installClaudeRouting({ paths: paths(arm), workspace: layout.workspace(arm), remote: preparation.remote }));
      }
      return installed;
    }

    if (options.stage === "freeze-claude") {
      const capture = (arm: string) => captureArm({
        home: layout.home(arm), workspace: layout.workspace(arm), sourceHome: preparation.sourceHome, engine: "claude-code",
      });
      const arms = { original: await capture("original"), "first-time": await capture("first-time"), deep: await capture("deep") };
      await ownedWrite({ path: layout.armsClaude, content: JSON.stringify(arms, null, 2) });
      return { original: arms.original.files.length, "first-time": arms["first-time"].files.length, deep: arms.deep.files.length };
    }

    const arms = {
      original: await captureArm({ home: layout.home("original"), workspace: layout.workspace("original"), sourceHome: preparation.sourceHome }),
      "first-time": await captureArm({ home: layout.home("first-time"), workspace: layout.workspace("first-time"), sourceHome: preparation.sourceHome }),
      deep: await captureArm({ home: layout.home("deep"), workspace: layout.workspace("deep"), sourceHome: preparation.sourceHome }),
    };
    await ownedWrite({ path: layout.arms, content: JSON.stringify(arms, null, 2) });
    return Object.fromEntries(Object.entries(arms).map(([arm, environment]) => [arm, environment.files.length]));
  } finally {
    await release();
  }
}
