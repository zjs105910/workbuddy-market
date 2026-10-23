import { z } from "zod";
import { applyBuild, type BuildPlan, lastBuildRevision, previewBuild } from "@shadowclone/builds";
import { buildView } from "./view";
import { reviewBuild } from "./review";
import { createModelActions } from "./modelActions";
import type { GenerationEngine } from "./generationEngine";
import { authorizeBrowserRequest, browserJson } from "./security";
import { learningModelCatalog, saveLearningModel } from "@shadowclone/learning";
import { type BuildContext, buildScopeSchema, undoRevision } from "@shadowclone/environment";

const previewRequestSchema = z.strictObject({ previewId: z.uuid() });
const revisionRequestSchema = z.strictObject({ revisionId: z.uuid() });

export function createBrowserHandler(
  context: BuildContext & {
    readonly token: string;
    readonly origin: () => string;
    readonly engine?: GenerationEngine;
    readonly botHandler?: (request: Request) => Promise<Response>;
  },
) {
  const previews = new Map<string, BuildPlan>();
  const revisions = new Set<string>();
  const modelAction = createModelActions(context);

  return async (request: Request): Promise<Response> => {
    if (
      !authorizeBrowserRequest({
        request,
        token: context.token,
        origin: context.origin(),
      })
    ) {
      return browserJson({
        status: 403,
        body: {
          error: "Open the local link printed by your CLI to use this editor.",
        },
      });
    }

    const url = new URL(request.url);

    try {
      if (url.pathname.startsWith("/api/bot/") && context.botHandler) {
        return context.botHandler(request);
      }

      if (request.method === "GET" && url.pathname === "/api/learning-models") {
        return browserJson({ body: await learningModelCatalog(context.paths) });
      }
      if (request.method === "GET" && url.pathname === "/api/build") {
        const scope = buildScopeSchema.parse(url.searchParams.get("scope") ?? "global");
        const revisionId = await lastBuildRevision({ ...context, scope });

        if (revisionId) {
          revisions.add(revisionId);
        }

        const view = await buildView({
          ...context,
          scope,
          revisionId,
        });

        return browserJson({ body: view });
      }

      if (request.method !== "POST") {
        return browserJson({
          status: 404,
          body: { error: "Unknown editor action" },
        });
      }

      if (request.headers.get("content-type") !== "application/json") {
        return browserJson({
          status: 415,
          body: { error: "Expected a JSON action" },
        });
      }

      const body: unknown = await request.json();
      if (url.pathname === "/api/learning-model") {
        await saveLearningModel({ paths: context.paths, input: body });
        return browserJson({ body: { saved: true } });
      }
      const generated = await modelAction({
        pathname: url.pathname,
        body,
        signal: request.signal,
      });

      if (generated) {
        return generated;
      }

      if (url.pathname === "/api/preview") {
        const plan = await previewBuild({ ...context, input: body });
        const id = crypto.randomUUID();

        previews.clear();
        previews.set(id, plan);

        return browserJson({ body: reviewBuild({ ...context, plan, id }) });
      }

      if (url.pathname === "/api/apply") {
        const { previewId } = previewRequestSchema.parse(body);
        const plan = previews.get(previewId);

        if (!plan) {
          throw new Error("Review a fresh preview before applying this build");
        }

        previews.delete(previewId);

        const latestRevision = await applyBuild({ ...context, plan });

        if (latestRevision !== null) {
          revisions.add(latestRevision);
        }

        return browserJson({ body: { revisionId: latestRevision } });
      }

      if (url.pathname === "/api/undo") {
        const { revisionId } = revisionRequestSchema.parse(body);

        if (!revisions.has(revisionId)) {
          throw new Error("Use shadowclone history to review older revisions before undoing them");
        }

        const reversed = await undoRevision({
          paths: context.paths,
          id: revisionId,
        });

        revisions.delete(revisionId);

        return browserJson({ body: { revisionId: reversed } });
      }

      return browserJson({
        status: 404,
        body: { error: "Unknown editor action" },
      });
    } catch (error) {
      const message =
        error instanceof z.ZodError
          ? "The editor input is invalid; reload and review the selected skills"
          : error instanceof Error
            ? error.message
            : "The editor action failed";

      return browserJson({ status: 400, body: { error: message } });
    }
  };
}
