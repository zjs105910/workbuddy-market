import { z } from "zod";
import { exportGuidance } from "../export";
import { cloneSchema, type Clone, type Delivery, type Repository } from "../types";
import { saveInstallation } from "../status";
import { verifyInstallation } from "./installation";
import { configureEnvironment } from "./environment";
import { protectDefaultBranch } from "./ruleset";
import { openWorkflowChange } from "./pull";
import { readCloudChecklist, type ChecklistItem } from "./checklist";
import type { GhApiCall } from "./ghApi";
import { assertCloudPolicy } from "./managedPolicy";
import { addSkillsDeployKey, ensureSkillsRepository, pushSkills } from "./skillsRepository";
import type { App } from "./app";
import type { GhCommand, GithubApi } from "./github";
import type { BuildContext } from "@shadowclone/environment";

export type ReviewedSetup = {
  readonly id: string;
  readonly repository: Repository;
  readonly owner: string;
  readonly name: string;
  readonly skills: readonly string[];
  readonly delivery: Delivery;
};

export async function activateClone(
  options: BuildContext & {
    readonly preview: ReviewedSetup;
    readonly app: App;
    readonly command: GhCommand;
    readonly api: GithubApi;
    readonly call: GhApiCall;
  },
): Promise<{ readonly clone: Clone; readonly pullUrl: string | null; readonly checklist: readonly ChecklistItem[] }> {
  const { preview, app, command, api, call } = options;

  await assertCloudPolicy({ paths: options.paths, engine: "claude" });

  const current = await exportGuidance({ ...options, skills: preview.skills });

  if (current.fingerprint !== preview.delivery.fingerprint) {
    throw new Error("The selected guidance changed. Review a fresh preview before uploading.");
  }

  const installation = await verifyInstallation({
    app,
    repository: preview.repository,
    api,
  });
  const bot = z
    .object({
      id: z.number().int().positive(),
      login: z.string(),
      type: z.literal("Bot"),
    })
    .parse(
      await api({
        route: `GET /users/${encodeURIComponent(`${app.slug}[bot]`)}`,
        token: installation.token,
      }),
    );

  await protectDefaultBranch({ repository: preview.repository, identity: "app", command });

  const skillsRepository = await ensureSkillsRepository({ call, owner: preview.owner });

  await pushSkills({ call, repository: skillsRepository, files: current.files });
  await configureEnvironment({
    repository: preview.repository,
    command,
    secrets: {
      SHADOWCLONE_APP_PRIVATE_KEY: app.pem,
      SHADOWCLONE_SKILLS_KEY: await addSkillsDeployKey({ call, skillsRepository, target: preview.repository.full_name }),
    },
  });

  const clone = cloneSchema.parse({
    repositoryId: preview.repository.id,
    repository: preview.repository.full_name,
    defaultBranch: preview.repository.default_branch,
    owner: preview.owner,
    identity: { kind: "app", appId: app.id },
    botId: bot.id,
    botLogin: bot.login,
    skillsRepository,
    requesters: [preview.owner],
    reviewerBots: ["coderabbitai[bot]", "github-actions[bot]"],
    maximumRuns: 10,
  });
  const pullUrl = await openWorkflowChange({ clone, api, token: installation.token });

  await saveInstallation({
    paths: options.paths,
    installation: {
      clone,
      pullUrl,
      guidanceFingerprint: current.fingerprint,
      installedAt: new Date().toISOString(),
    },
  });

  return { clone, pullUrl, checklist: await readCloudChecklist({ call, clone, pullUrl }) };
}
