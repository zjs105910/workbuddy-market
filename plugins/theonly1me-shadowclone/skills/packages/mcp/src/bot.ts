import { z } from "zod";
import { serveBuildWizard } from "@shadowclone/web";
import {
  type AccountSetupOutcome,
  checklistText,
  cloneStatus,
  ghApiCall,
  type GhApiCall,
  type GhCommand,
  openPage,
  pendingPages,
  readCloudChecklist,
  readInstallation,
  runGh,
  setUpAccountClone,
} from "@shadowclone/cloud";
import { isRecord } from "./protocol";
import type { BuildContext } from "@shadowclone/environment";

export const botTools = [
  {
    name: "shadowclone_bot",
    description:
      "Set up the Shadowclone cloud bot for a GitHub repository, or read its setup status. " +
      "With bot, setup uses a machine account with that login: it invites the bot, protects " +
      "the default branch, pushes the owner's skills to a private repository, and opens the " +
      "setup pull request. The owner enters every token on GitHub, never here. The first " +
      "setup call returns the skill files; show them to the owner and call again with " +
      "approveSkills true only after the owner agrees. Without bot, setup opens the local " +
      "wizard, which also offers a GitHub App.",
    inputSchema: {
      type: "object",
      properties: {
        operation: { type: "string", enum: ["setup", "status"] },
        repository: { type: "string", description: "owner/repository" },
        bot: { type: "string", description: "GitHub login of the bot's machine account" },
        approveSkills: { type: "boolean", description: "true only after the owner approved the listed skill files" },
        engine: { type: "string", enum: ["claude", "codex"], description: "the agent that works and reviews; defaults to claude" },
        codexAuth: { type: "string", enum: ["api-key", "plan"], description: "Codex sign-in; plan is experimental" },
      },
      required: ["operation"],
      additionalProperties: false,
    },
  },
];

const inputSchema = z.strictObject({
  operation: z.enum(["setup", "status"]),
  repository: z
    .string()
    .regex(/^[\w.-]+\/[\w.-]+$/)
    .optional(),
  bot: z
    .string()
    .regex(/^[A-Za-z0-9-]{1,39}$/)
    .optional(),
  approveSkills: z.boolean().optional(),
  engine: z.enum(["claude", "codex"]).default("claude"),
  codexAuth: z.enum(["api-key", "plan"]).default("api-key"),
});

function text(options: { readonly value: string; readonly isError?: boolean }) {
  return { content: [{ type: "text", text: options.value }], isError: options.isError ?? false };
}

async function outcomeText(outcome: AccountSetupOutcome): Promise<string> {
  if (outcome.kind === "needs-account") {
    await openPage(outcome.signupUrl);
    return `The GitHub account ${outcome.login} does not exist. The signup page is open. Ask the owner to create it, then call setup again.`;
  }

  if (outcome.kind === "needs-approval") {
    return [
      `Setup pushes these ${outcome.files.length} files to the private repository ${outcome.skillsRepository}:`,
      ...outcome.files.map((file) => `- ${file.path} (${file.bytes} bytes)`),
      "Show this list to the owner. Call setup again with approveSkills true only after the owner agrees.",
    ].join("\n");
  }

  for (const url of pendingPages(outcome.checklist)) {
    await openPage(url);
  }

  return `${[...outcome.warnings, checklistText(outcome.checklist)].join("\n\n")}\n\nThe pages for the open steps are open in the browser. Call status to check progress.`;
}

export function createBotTool(context: BuildContext & { readonly call?: GhApiCall; readonly command?: GhCommand }) {
  const call = context.call ?? ghApiCall;
  const command = context.command ?? runGh;
  let wizard: ReturnType<typeof serveBuildWizard> | null = null;

  return {
    stop: () => wizard?.stop(),
    run: async (params: unknown) => {
      if (!isRecord(params) || params.name !== "shadowclone_bot") {
        return null;
      }

      const input = inputSchema.safeParse(params.arguments);

      if (!input.success) {
        return text({
          value: "Use operation setup or status, with optional repository, bot, and approveSkills. Tokens go on GitHub, never here.",
          isError: true,
        });
      }

      const { operation, repository, bot } = input.data;

      try {
        if (operation === "status") {
          const installation = repository ? await readInstallation({ paths: context.paths, repository }) : null;

          return text({
            value: installation
              ? checklistText(await readCloudChecklist({ call, clone: installation.clone, pullUrl: installation.pullUrl }))
              : JSON.stringify(await cloneStatus(context.paths)),
          });
        }

        if (bot === undefined || repository === undefined) {
          if (bot !== undefined) {
            return text({ value: "Name the repository as owner/repository to set up a machine account bot.", isError: true });
          }

          wizard ??= serveBuildWizard({ ...context, bot: true });

          return text({
            value: `Open ${wizard.url}. Choose a machine account or a GitHub App there. Keep this MCP connection open until setup finishes.`,
          });
        }

        return text({
          value: await outcomeText(
            await setUpAccountClone({
              ...context,
              repository,
              botLogin: bot,
              approveSkills: input.data.approveSkills === true,
              engine: input.data.engine,
              codexAuth: input.data.codexAuth,
              call,
              command,
            }),
          ),
        });
      } catch (error) {
        return text({ value: error instanceof Error ? error.message : "Setup could not complete.", isError: true });
      }
    },
  };
}
