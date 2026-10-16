import { z } from "zod";
import type { Clone } from "../types";
import { readBotAccess } from "./account";
import type { GhApiCall } from "./ghApi";

export type ChecklistLink = { readonly label: string; readonly url: string };

export type ChecklistItem = {
  readonly key: "bot-token" | "app-key" | "model-token" | "skills" | "workflows" | "invitation";
  readonly done: boolean;
  readonly title: string;
  readonly action: string;
  readonly links: readonly ChecklistLink[];
};

const environmentSchema = z.object({ id: z.number().int().positive() });
const secretsSchema = z.object({ secrets: z.array(z.object({ name: z.string() })) });

export function botTokenPage(repository: string): string {
  const page = new URL("https://github.com/settings/tokens/new");

  page.searchParams.set("scopes", "repo");
  page.searchParams.set("description", `shadowclone ${repository}`);

  return page.toString();
}

async function environmentState(options: {
  readonly call: GhApiCall;
  readonly repository: string;
}) {
  const environment = await options.call({
    route: `repos/${options.repository}/environments/shadowclone`,
  });

  if (environment.status !== 200) {
    return {
      page: `https://github.com/${options.repository}/settings/environments`,
      secrets: new Set<string>(),
    };
  }

  const secrets = await options.call({
    route: `repos/${options.repository}/environments/shadowclone/secrets?per_page=100`,
  });

  return {
    page: `https://github.com/${options.repository}/settings/environments/${environmentSchema.parse(environment.data).id}/edit`,
    secrets: new Set(
      secrets.status === 200
        ? secretsSchema.parse(secrets.data).secrets.map((secret) => secret.name)
        : [],
    ),
  };
}

function modelToken(clone: Clone): { readonly secret: string; readonly title: string; readonly action: string } {
  if (clone.engine === "claude") {
    return {
      secret: "CLAUDE_CODE_OAUTH_TOKEN",
      title: "Claude token",
      action: "Run claude setup-token in a terminal, and add the token to the environment as CLAUDE_CODE_OAUTH_TOKEN.",
    };
  }

  return clone.codexAuth === "plan"
    ? {
        secret: "CODEX_AUTH_JSON",
        title: "Codex login (experimental)",
        action: "Run codex login on your machine, and add the content of ~/.codex/auth.json to the environment as CODEX_AUTH_JSON.",
      }
    : {
        secret: "OPENAI_API_KEY",
        title: "OpenAI API key",
        action: "Create an API key in the OpenAI platform, and add it to the environment as OPENAI_API_KEY.",
      };
}

export async function readCloudChecklist(options: {
  readonly call: GhApiCall;
  readonly clone: Clone;
  readonly pullUrl: string | null;
}): Promise<readonly ChecklistItem[]> {
  const { call, clone } = options;
  const environment = await environmentState({ call, repository: clone.repository });
  const environmentLink = { label: "Environment secrets", url: environment.page };
  const relay = await call({
    route: `repos/${clone.repository}/contents/.github/workflows/shadowclone-relay.yml?ref=${encodeURIComponent(clone.defaultBranch)}`,
  });
  const identity: ChecklistItem =
    clone.identity.kind === "account"
      ? {
          key: "bot-token",
          done: environment.secrets.has("SHADOWCLONE_BOT_TOKEN"),
          title: `Token for ${clone.botLogin}`,
          action: `Sign in to GitHub as ${clone.botLogin}, create a classic token with only the repo scope, and add it to the environment as SHADOWCLONE_BOT_TOKEN.`,
          links: [
            { label: "Create the token", url: botTokenPage(clone.repository) },
            environmentLink,
          ],
        }
      : {
          key: "app-key",
          done: environment.secrets.has("SHADOWCLONE_APP_PRIVATE_KEY"),
          title: "App key",
          action: "Run shadowclone bot setup --app again to upload the App key.",
          links: [environmentLink],
        };
  const model = modelToken(clone);
  const items: ChecklistItem[] = [
    identity,
    {
      key: "model-token",
      done: environment.secrets.has(model.secret),
      title: model.title,
      action: model.action,
      links: [environmentLink],
    },
    {
      key: "skills",
      done: environment.secrets.has("SHADOWCLONE_SKILLS_KEY"),
      title: `Skills from ${clone.skillsRepository}`,
      action: "Run shadowclone bot setup again to push the skills and add their deploy key.",
      links: [{ label: "Skills repository", url: `https://github.com/${clone.skillsRepository}` }],
    },
    {
      key: "workflows",
      done: relay.status === 200,
      title: `Workflows on ${clone.defaultBranch}`,
      action: "Review and merge the setup pull request.",
      links:
        options.pullUrl === null ? [] : [{ label: "Setup pull request", url: options.pullUrl }],
    },
  ];

  if (clone.identity.kind === "account") {
    const access = await readBotAccess({
      call,
      repository: clone.repository,
      login: clone.botLogin,
    });

    items.push({
      key: "invitation",
      done: access === "collaborator",
      title: `${clone.botLogin} joined the repository`,
      action:
        access === "invited"
          ? `After the merge, mention @${clone.botLogin} once. Its first run accepts the invitation.`
          : "Run shadowclone bot setup again to invite the bot.",
      links: [],
    });
  }

  return items;
}
