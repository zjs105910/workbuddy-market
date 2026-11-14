import type { GitRemoteReader } from "@shadowclone/sessions";
import { exportGuidance } from "../export";
import { saveInstallation } from "../status";
import { defaultCodexReviewModel } from "@shadowclone/review";
import { cloneSchema, type Clone } from "../types";
import { inviteBot, readBotAccess, readBotAccount } from "./account";
import { readCloudChecklist, type ChecklistItem } from "./checklist";
import { configureEnvironment } from "./environment";
import { githubApiThroughGh, type GhApiCall } from "./ghApi";
import type { GhCommand } from "./github";
import { assertCloudPolicy } from "./managedPolicy";
import { openWorkflowChange } from "./pull";
import { protectDefaultBranch } from "./ruleset";
import { setupSelection } from "./selection";
import {
  addSkillsDeployKey,
  ensureSkillsRepository,
  pushSkills,
  skillsRepositoryName,
} from "./skillsRepository";
import { readSetupTarget } from "./target";
import type { BuildContext } from "@shadowclone/environment";

export type AccountSetupOutcome =
  | { readonly kind: "needs-account"; readonly login: string; readonly signupUrl: string }
  | {
      readonly kind: "needs-approval";
      readonly skillsRepository: string;
      readonly files: readonly { readonly path: string; readonly bytes: number }[];
    }
  | {
      readonly kind: "configured";
      readonly clone: Clone;
      readonly pullUrl: string | null;
      readonly checklist: readonly ChecklistItem[];
      readonly warnings: readonly string[];
    };

export const organizationMergeWarning =
  "In this organization repository, only admins and maintainers can now update the default branch, because the bot has the write role. Write-role members need one of them to merge.";

export async function setUpAccountClone(
  options: BuildContext & {
    readonly repository: string;
    readonly botLogin: string;
    readonly approveSkills: boolean;
    readonly engine: "claude" | "codex";
    readonly codexAuth: "api-key" | "plan";
    readonly call: GhApiCall;
    readonly command: GhCommand;
    readonly readRemote?: GitRemoteReader;
  },
): Promise<AccountSetupOutcome> {
  const { call, command } = options;

  await assertCloudPolicy({ paths: options.paths, engine: options.engine });

  if (options.codexAuth === "plan" && options.engine !== "codex") {
    throw new Error("A ChatGPT plan login works only with the Codex engine.");
  }

  const { owner, repository } = await readSetupTarget(options);
  const bot = await readBotAccount({ call, login: options.botLogin });

  if (bot === null) {
    return {
      kind: "needs-account",
      login: options.botLogin,
      signupUrl: "https://github.com/signup",
    };
  }

  if (bot.login.toLowerCase() === owner.toLowerCase()) {
    throw new Error("The bot needs its own GitHub account. Create a machine account for it.");
  }

  const { skills } = await setupSelection(options);
  const delivery = await exportGuidance({
    paths: options.paths,
    cwd: options.cwd,
    skills,
    readRemote: options.readRemote,
  });

  if (!options.approveSkills) {
    return {
      kind: "needs-approval",
      skillsRepository: `${owner}/${skillsRepositoryName}`,
      files: delivery.files.map((file) => ({
        path: file.path,
        bytes: Buffer.from(file.content, "base64").length,
      })),
    };
  }

  await protectDefaultBranch({ repository, identity: "account", command });

  const skillsRepository = await ensureSkillsRepository({ call, owner });

  await pushSkills({ call, repository: skillsRepository, files: delivery.files });
  await configureEnvironment({
    repository,
    command,
    secrets: {
      SHADOWCLONE_SKILLS_KEY: await addSkillsDeployKey({
        call,
        skillsRepository,
        target: repository.full_name,
      }),
    },
  });

  if (
    (await readBotAccess({ call, repository: repository.full_name, login: bot.login })) === "none"
  ) {
    await inviteBot({ call, repository: repository.full_name, login: bot.login });
  }

  const clone = cloneSchema.parse({
    repositoryId: repository.id,
    repository: repository.full_name,
    defaultBranch: repository.default_branch,
    owner,
    identity: { kind: "account" },
    botId: bot.id,
    botLogin: bot.login,
    skillsRepository,
    requesters: [owner],
    reviewerBots: ["coderabbitai[bot]", "github-actions[bot]"],
    maximumRuns: 10,
    engine: options.engine,
    codexAuth: options.codexAuth,
    reviewModel: options.engine === "codex" ? defaultCodexReviewModel : "claude-opus-5-5",
  });
  const pullUrl = await openWorkflowChange({ clone, api: githubApiThroughGh(call) });

  await saveInstallation({
    paths: options.paths,
    installation: {
      clone,
      pullUrl,
      guidanceFingerprint: delivery.fingerprint,
      installedAt: new Date().toISOString(),
    },
  });

  return {
    kind: "configured",
    clone,
    pullUrl,
    checklist: await readCloudChecklist({ call, clone, pullUrl }),
    warnings: repository.owner.type === "Organization" ? [organizationMergeWarning] : [],
  };
}
