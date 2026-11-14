import { expect, test } from "bun:test";
import { verifyInstallation } from "./installation";
import { syntheticApp, setupRepository } from "./fixtures";
import type { GithubApi } from "./github";

function installationApi(options: { readonly selection?: string; readonly repositoryId?: number }) {
  const calls: { route: string; body?: unknown }[] = [];
  const api: GithubApi = async ({ route, body }) => {
    calls.push({ route, body });

    if (route.startsWith("GET /app/installations")) {
      return [
        {
          id: 40,
          app_id: 20,
          repository_selection: options.selection ?? "selected",
          suspended_at: null,
          account: { login: "sample" },
        },
      ];
    }

    if (route.startsWith("POST /app/installations")) {
      return { token: "synthetic-installation-token", repository_selection: "selected" };
    }

    if (route.startsWith("GET /installation/repositories")) {
      return { repositories: [{ id: options.repositoryId ?? 10, full_name: "sample/project" }] };
    }

    throw new Error("Unexpected installation route.");
  };

  return { api, calls };
}

test("All repositories is rejected before minting an installation token", async () => {
  const fixture = installationApi({ selection: "all" });

  await expect(
    verifyInstallation({ app: syntheticApp(), repository: setupRepository, api: fixture.api }),
  ).rejects.toThrow("All repositories");
  expect(fixture.calls).toHaveLength(1);
});

test("the installation token requests exactly the reviewed repository ID", async () => {
  const fixture = installationApi({});
  const result = await verifyInstallation({
    app: syntheticApp(),
    repository: setupRepository,
    api: fixture.api,
  });
  const mint = fixture.calls.find((call) => call.route.startsWith("POST"));

  expect(result.installationId).toBe(40);
  expect(mint?.body).toMatchObject({ repository_ids: [10] });
});

test("a repository ID mismatch prevents setup", async () => {
  const fixture = installationApi({ repositoryId: 99 });

  await expect(
    verifyInstallation({ app: syntheticApp(), repository: setupRepository, api: fixture.api }),
  ).rejects.toThrow("repository ID");
});
