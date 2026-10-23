import { z } from "zod";
import { resolveRepository, type GitRemoteReader } from "@shadowclone/sessions";
import {
  activateClone,
  type App,
  appManifest,
  type Clone,
  createManifestCallback,
  exportGuidance,
  ghApiCall,
  type GhApiCall,
  type GhCommand,
  githubApi,
  type GithubApi,
  previewApprovalSchema,
  readCloudChecklist,
  repositorySchema,
  type ReviewedSetup,
  runGh,
  setupPreviewInput,
  setupSelection,
} from "@shadowclone/cloud";
import { browserJson } from "../security";
import { handleAccountSetup } from "./browserAccount";
import type { BuildContext } from "@shadowclone/environment";

export function createBotBrowser(
  context: BuildContext & {
    readonly origin: () => string;
    readonly command?: GhCommand;
    readonly api?: GithubApi;
    readonly readRemote?: GitRemoteReader;
    readonly call?: GhApiCall;
  },
) {
  const command = context.command ?? runGh;
  const api = context.api ?? githubApi;
  const call = context.call ?? ghApiCall;
  let preview: ReviewedSetup | null = null;
  let app: App | null = null;
  let callback: ReturnType<typeof createManifestCallback> | null = null;
  let pullUrl: string | null = null;
  let activated: Clone | null = null;
  let busy = false;
  const expires = Date.now() + 3_600_000;

  return async (request: Request): Promise<Response> => {
    const url = new URL(request.url);

    if (url.pathname === "/api/bot/callback") {
      return callback
        ? callback.handle(request)
        : browserJson({
            status: 403,
            body: { error: "Start setup before registering the App." },
          });
    }

    if (Date.now() > expires) {
      return browserJson({
        status: 403,
        body: { error: "The setup session expired. Start a fresh session." },
      });
    }

    if (request.method === "GET" && url.pathname === "/api/bot/state") {
      const selection = await setupSelection(context);

      return browserJson({
        body: {
          repository: preview?.repository.full_name ?? selection.repository,
          skills: selection.skills,
          previewId: app ? (preview?.id ?? null) : null,
          checklist: activated ? await readCloudChecklist({ call, clone: activated, pullUrl }) : null,
          app: app
            ? {
                name: app.slug,
                installUrl: `https://github.com/apps/${app.slug}/installations/new`,
              }
            : null,
          pullUrl,
        },
      });
    }

    if (request.method !== "POST" || request.headers.get("content-type") !== "application/json") {
      return browserJson({
        status: 400,
        body: { error: "Expected a JSON setup action." },
      });
    }

    if (url.pathname === "/api/bot/account") {
      return handleAccountSetup({ ...context, request, call, command });
    }

    if (busy || activated) {
      return browserJson({
        status: 409,
        body: { error: "The setup is already running or complete." },
      });
    }

    busy = true;

    try {
      const body: unknown = await request.json();

      if (url.pathname === "/api/bot/preview") {
        if (app) {
          throw new Error("Finish the current App setup before changing its scope.");
        }

        const input = setupPreviewInput.parse(body);
        const owner = z
          .object({ login: z.string().regex(/^[\w-]+$/) })
          .parse(JSON.parse(await command({ arguments: ["api", "user"] }))).login;
        const repository = repositorySchema.parse(
          JSON.parse(await command({ arguments: ["api", `repos/${input.repository}`] })),
        );
        const local = await resolveRepository({
          cwd: context.cwd,
          enabled: true,
          readRemote: context.readRemote,
        });

        if (local?.id !== `github.com/${repository.full_name.toLowerCase()}`) {
          throw new Error(
            "Start setup in the reviewed repository checkout. Its origin must match the " +
              "selected repository.",
          );
        }

        if (!repository.permissions.admin) {
          throw new Error(
            "The signed-in GitHub account needs administration access to configure this " +
              "repository.",
          );
        }

        if (repository.owner.type === "User" && repository.owner.login !== owner) {
          throw new Error("A private personal App must belong to the selected repository owner.");
        }

        const delivery = await exportGuidance({
          ...context,
          skills: input.skills,
        });

        preview = {
          id: crypto.randomUUID(),
          repository,
          owner,
          name: input.name,
          skills: input.skills,
          delivery,
        };

        callback = null;

        return browserJson({
          body: {
            id: preview.id,
            repository: repository.full_name,
            repositoryId: repository.id,
            owner,
            appOwner: repository.owner.login,
            fingerprint: delivery.fingerprint,
            bytes: delivery.files.reduce((total, file) => total + Buffer.from(file.content, "base64").length, 0),
            files: delivery.files.map((file) => ({
              path: file.path,
              content: file.content,
            })),
          },
        });
      }

      const approval = previewApprovalSchema.safeParse(body);
      const previewId = approval.success ? approval.data.previewId : null;

      if (!preview || previewId !== preview.id) {
        throw new Error("Review and approve the exact guidance preview before setup.");
      }

      if (url.pathname === "/api/bot/manifest" && approval.success) {
        if (callback || app) {
          throw new Error("The App registration already started.");
        }

        callback = createManifestCallback({
          origin: context.origin,
          owner: preview.repository.owner.login,
          api,
          onApp: async (created) => {
            app = created;
          },
        });
        const account = preview.repository.owner;
        const registration =
          account.type === "Organization"
            ? `/organizations/${account.login}/settings/apps/new`
            : "/settings/apps/new";
        const action = new URL(registration, "https://github.com");

        action.searchParams.set("state", callback.state);

        return browserJson({
          body: {
            action: action.toString(),
            manifest: JSON.stringify(appManifest({ name: preview.name, origin: context.origin() })),
          },
        });
      }

      if (url.pathname === "/api/bot/activate" && app) {
        const result = await activateClone({ ...context, preview, app, command, api, call });

        pullUrl = result.pullUrl;
        activated = result.clone;
        app = null;

        return browserJson({
          body: {
            repository: preview.repository.full_name,
            app: null,
            pullUrl,
            checklist: result.checklist,
          },
        });
      }

      throw new Error(
        "Complete the reviewed App registration and installation before uploading " +
          "credentials.",
      );
    } catch (error) {
      return browserJson({
        status: 400,
        body: {
          error:
            url.pathname !== "/api/bot/preview" || !(error instanceof Error)
              ? "Setup could not complete. Verify the selected repository, portable " +
                "guidance, App installation, and environment policy. No credentials appear " +
                "in diagnostics."
              : error instanceof z.ZodError
                ? "Enter the repository as owner/repository, a clone name, and 1 to 40 " +
                  "skill names."
                : error.message,
        },
      });
    } finally {
      busy = false;
    }
  };
}
