import { z } from "zod";
import { listRevisions } from "@shadowclone/changes";
import { readEffectiveConfig } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { rememberPreference } from "@shadowclone/learning";
import type { GitRemoteReader } from "@shadowclone/sessions";
import { readMaintenanceState, listSkillProposals } from "@shadowclone/skills";
import { environmentStatus } from "@shadowclone/environment";

export const preferenceTools = [
  {
    name: "shadowclone_skills_status",
    description:
      "Inspect configured skill-root and pending-review counts without reading skill contents or making a model call. Use the CLI to review or update skills.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
  {
    name: "shadowclone_remember",
    description:
      "Record an explicit user-requested engineering preference locally. Never infer consent from a task or interruption. This does not authorize execution.",
    inputSchema: {
      type: "object",
      properties: {
        text: { type: "string", maxLength: 8192 },
        scope: { type: "string", enum: ["repository", "global"] },
      },
      required: ["text", "scope"],
      additionalProperties: false,
    },
  },
  {
    name: "shadowclone_history",
    description:
      "Inspect local revision identifiers, times and counts without exposing guidance from other repositories. Use the CLI to review or undo a specific revision.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
  },
];

const callSchema = z.object({
  name: z.string(),
  arguments: z.unknown().optional(),
});
const rememberSchema = z.strictObject({
  text: z.string().min(1).max(8192),
  scope: z.enum(["repository", "global"]),
});

export async function runPreferenceTool(options: {
  readonly params: unknown;
  readonly paths: ProjectPaths;
  readonly cwd: string;
  readonly managedConfigPath?: string | null;
  readonly readRemote?: GitRemoteReader;
}): Promise<{
  readonly content: readonly { readonly type: "text"; readonly text: string }[];
  readonly isError: boolean;
} | null> {
  const call = callSchema.safeParse(options.params);

  if (
    !call.success ||
    !preferenceTools.some((tool) => tool.name === call.data.name)
  ) {
    return null;
  }

  try {
    const { policy } = await readEffectiveConfig({
      configPath: options.paths.configFile,
      managedConfigPath:
        options.managedConfigPath === undefined
          ? options.paths.managedConfigFile
          : options.managedConfigPath,
    });

    if (!policy.enabled) {
      throw new Error("Shadowclone is disabled");
    }

    let text: string;

    if (call.data.name === "shadowclone_remember") {
      const parameters = rememberSchema.safeParse(call.data.arguments);

      if (!parameters.success) {
        throw new Error("Invalid preference parameters");
      }

      const key = await rememberPreference({ ...options, ...parameters.data });

      text = `Recorded preference ${key}.`;
    } else {
      if (!z.strictObject({}).safeParse(call.data.arguments ?? {}).success) {
        throw new Error("Invalid history parameters");
      }

      if (call.data.name === "shadowclone_skills_status") {
        const state = await readMaintenanceState(options.paths);
        const proposals = await listSkillProposals(options.paths);
        const environment = await environmentStatus(options.paths);

        text = JSON.stringify({
          roots: state.roots.filter((root) => root.enabled).length,
          managed:
            environment?.skills ??
            state.tracked.filter((skill) => skill.automatic).length,
          pending:
            environment?.pending ??
            proposals.filter((proposal) => proposal.status === "pending")
              .length,
          ...(environment ? { environment } : {}),
        });
      } else {
        text = JSON.stringify(await listRevisions(options.paths));
      }
    }

    return { content: [{ type: "text", text }], isError: false };
  } catch {
    return {
      content: [
        {
          type: "text",
          text: "Preference operation was not applied. Check parameters, policy and local file conflicts with shadowclone doctor.",
        },
      ],
      isError: true,
    };
  }
}
