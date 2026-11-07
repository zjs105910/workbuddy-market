import { z } from "zod";
import { appJwt, type App } from "./app";
import type { GithubApi } from "./github";
import type { Repository } from "../types";

const installationSchema = z.object({
  id: z.number().int().positive(),
  app_id: z.number().int().positive(),
  repository_selection: z.enum(["all", "selected"]),
  suspended_at: z.string().nullable(),
  account: z.object({ login: z.string() }),
});
const tokenSchema = z.object({
  token: z.string().min(1),
  repository_selection: z.literal("selected"),
});
const repositoriesSchema = z.object({
  repositories: z.array(z.object({ id: z.number().int().positive(), full_name: z.string() })),
});

export async function verifyInstallation(options: {
  readonly app: App;
  readonly repository: Repository;
  readonly api: GithubApi;
}): Promise<{ readonly installationId: number; readonly token: string }> {
  const jwt = appJwt(options.app);
  const installations = z.array(installationSchema).parse(
    await options.api({
      route: "GET /app/installations?per_page=100",
      token: jwt,
    }),
  );
  const installation = installations.find(
    (entry) =>
      entry.account.login.toLowerCase() === options.repository.owner.login.toLowerCase() &&
      entry.app_id === options.app.id,
  );

  if (!installation || installation.suspended_at !== null) {
    throw new Error("Install the App on the target account before continuing.");
  }

  if (installation.repository_selection !== "selected") {
    throw new Error("Choose Only select repositories. All repositories is not permitted.");
  }

  const granted = tokenSchema.parse(
    await options.api({
      route: `POST /app/installations/${installation.id}/access_tokens`,
      token: jwt,
      body: {
        repository_ids: [options.repository.id],
        permissions: {
          contents: "write",
          issues: "write",
          pull_requests: "write",
          actions: "write",
          checks: "read",
          workflows: "write",
        },
      },
    }),
  );
  const selected = repositoriesSchema.parse(
    await options.api({
      route: "GET /installation/repositories?per_page=100",
      token: granted.token,
    }),
  );
  const [repository] = selected.repositories;

  if (
    selected.repositories.length !== 1 ||
    repository?.id !== options.repository.id ||
    repository.full_name.toLowerCase() !== options.repository.full_name.toLowerCase()
  ) {
    throw new Error("The installation repository ID does not match the reviewed repository.");
  }

  return { installationId: installation.id, token: granted.token };
}
