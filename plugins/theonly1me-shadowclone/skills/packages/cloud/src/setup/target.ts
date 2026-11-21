import { z } from "zod";
import { resolveRepository, type GitRemoteReader } from "@shadowclone/sessions";
import { repositorySchema, type Repository } from "../types";
import { ghApiData, type GhApiCall } from "./ghApi";

export type SetupTarget = { readonly owner: string; readonly repository: Repository };

export async function readSetupTarget(options: {
  readonly call: GhApiCall;
  readonly repository: string;
  readonly cwd: string;
  readonly readRemote?: GitRemoteReader;
}): Promise<SetupTarget> {
  const owner = z
    .object({ login: z.string().regex(/^[\w-]+$/) })
    .parse(await ghApiData({ call: options.call, route: "user" })).login;
  const repository = repositorySchema.parse(
    await ghApiData({ call: options.call, route: `repos/${options.repository}` }),
  );
  const local = await resolveRepository({
    cwd: options.cwd,
    enabled: true,
    readRemote: options.readRemote,
  });

  if (local?.id !== `github.com/${repository.full_name.toLowerCase()}`) {
    throw new Error(
      "Run setup in a checkout of the repository. Its origin must match the selected repository.",
    );
  }

  if (!repository.permissions.admin) {
    throw new Error(
      "The signed-in GitHub account needs administration access to configure this repository.",
    );
  }

  return { owner, repository };
}
