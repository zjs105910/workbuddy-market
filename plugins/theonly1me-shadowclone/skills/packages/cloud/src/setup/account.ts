import { z } from "zod";
import { accountLoginPattern } from "../types";
import { ghApiData, type GhApiCall } from "./ghApi";

const userSchema = z.object({
  id: z.number().int().positive(),
  login: z.string(),
  type: z.string(),
});
const invitationsSchema = z.array(
  z.object({ invitee: z.object({ login: z.string() }).nullable() }),
);

export type BotAccount = { readonly id: number; readonly login: string };

export type BotAccess = "collaborator" | "invited" | "none";

export async function readBotAccount(options: {
  readonly call: GhApiCall;
  readonly login: string;
}): Promise<BotAccount | null> {
  if (!accountLoginPattern.test(options.login)) {
    throw new Error("Name the bot with its GitHub login, such as octo-shadow.");
  }

  const response = await options.call({ route: `users/${options.login}` });

  if (response.status === 404) {
    return null;
  }

  if (response.status >= 300) {
    throw new Error(`GitHub refused to read the account ${options.login} (${response.status}).`);
  }

  const user = userSchema.parse(response.data);

  if (user.type !== "User") {
    throw new Error(
      `${user.login} is not a user account. Use a machine account, or set up a GitHub App with --app.`,
    );
  }

  return { id: user.id, login: user.login };
}

export async function inviteBot(options: {
  readonly call: GhApiCall;
  readonly repository: string;
  readonly login: string;
}): Promise<void> {
  await ghApiData({
    call: options.call,
    method: "PUT",
    route: `repos/${options.repository}/collaborators/${options.login}`,
    body: { permission: "push" },
  });
}

export async function readBotAccess(options: {
  readonly call: GhApiCall;
  readonly repository: string;
  readonly login: string;
}): Promise<BotAccess> {
  const collaborator = await options.call({
    route: `repos/${options.repository}/collaborators/${options.login}`,
  });

  if (collaborator.status === 204) {
    return "collaborator";
  }

  const invitations = invitationsSchema.parse(
    await ghApiData({
      call: options.call,
      route: `repos/${options.repository}/invitations?per_page=100`,
    }),
  );

  return invitations.some(
    (invitation) => invitation.invitee?.login.toLowerCase() === options.login.toLowerCase(),
  )
    ? "invited"
    : "none";
}
