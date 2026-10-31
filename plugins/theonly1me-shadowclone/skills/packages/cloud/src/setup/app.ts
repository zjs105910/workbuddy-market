import { createPrivateKey, sign } from "node:crypto";
import { z } from "zod";
import type { GithubApi } from "./github";

export const appSchema = z.object({
  id: z.number().int().positive(),
  slug: z.string().regex(/^[a-z0-9-]+$/),
  pem: z.string().min(1),
  owner: z.object({ login: z.string() }),
});
export type App = z.infer<typeof appSchema>;

export function appJwt(app: App): string {
  const issued = Math.floor(Date.now() / 1000);
  const header = Buffer.from(JSON.stringify({ alg: "RS256", typ: "JWT" })).toString("base64url");
  const payload = Buffer.from(
    JSON.stringify({
      iat: issued - 60,
      exp: issued + 540,
      iss: String(app.id),
    }),
  ).toString("base64url");
  const unsigned = `${header}.${payload}`;

  return `${unsigned}.${sign("RSA-SHA256", Buffer.from(unsigned), createPrivateKey(app.pem)).toString("base64url")}`;
}

export function appManifest(options: { readonly name: string; readonly origin: string }) {
  return {
    name: options.name,
    url: "https://shadowclone.co",
    description: "A personal coding clone for explicitly selected repositories",
    public: false,
    hook_attributes: { url: "https://github.com", active: false },
    redirect_url: `${options.origin}/api/bot/callback`,
    setup_url: `${options.origin}/?bot=github`,
    setup_on_update: false,
    default_events: [],
    default_permissions: {
      contents: "write",
      issues: "write",
      pull_requests: "write",
      actions: "write",
      checks: "read",
      workflows: "write",
    },
    request_oauth_on_install: false,
  };
}

export function createManifestCallback(options: {
  readonly origin: () => string;
  readonly owner: string;
  readonly api: GithubApi;
  readonly onApp: (app: App) => Promise<void>;
}) {
  const state = `${crypto.randomUUID()}${crypto.randomUUID()}`;
  const expires = Date.now() + 3_600_000;
  let consumed = false;

  return {
    state,
    handle: async (request: Request): Promise<Response> => {
      const url = new URL(request.url);
      const code = url.searchParams.get("code");

      if (
        request.method !== "GET" ||
        url.origin !== options.origin() ||
        consumed ||
        Date.now() > expires ||
        url.searchParams.get("state") !== state ||
        !code ||
        !/^[A-Za-z0-9_-]{20,200}$/.test(code)
      ) {
        return new Response("Invalid or expired setup callback.", {
          status: 403,
        });
      }

      consumed = true;

      try {
        const app = appSchema.parse(
          await options.api({
            route: `POST /app-manifests/${code}/conversions`,
          }),
        );

        if (app.owner.login !== options.owner) {
          throw new Error("The App registration belongs to another account.");
        }

        await options.onApp(app);

        return new Response(null, {
          status: 303,
          headers: {
            Location: `${options.origin()}/?bot=github`,
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
          },
        });
      } catch {
        return new Response("App registration could not complete. Start a fresh setup session.", {
          status: 400,
        });
      }
    },
  };
}
