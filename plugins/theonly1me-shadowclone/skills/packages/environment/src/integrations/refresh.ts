import { fingerprint, readLocalText, projectPaths } from "@shadowclone/core";
import { compileContext } from "./compile";
import { applyIntegrationFiles, prepareIntegrationFiles, savedRecords } from "./files";
import { hasOwnedHooks } from "./hookConfig";
import { managedSection } from "./markdown";
import { readIntegrations, saveIntegration } from "./state";
import { integrationFilePath } from "./targets";
import type { IntegrationOptions } from "./types";
import { readEnvironment } from "../environment";
import { ensureHookRunner } from "./hookRunner";

export async function refreshIntegrations(
  options: IntegrationOptions = {},
): Promise<{ readonly refreshed: number; readonly preserved: number }> {
  const paths = options.paths ?? projectPaths;
  const environment = (await readEnvironment(paths))?.phase === "active";
  let refreshed = 0;
  let preserved = 0;

  for (const integration of await readIntegrations(paths)) {
    if (integration.agent === "claude-code" || integration.agent === "codex" || integration.agent === "pi") {
      await ensureHookRunner({ paths });
    }
    const profile = await compileContext({
      ...options,
      paths,
      cwd: integration.directory,
      scope: integration.scope === "global" ? "global" : "combined",
    });

    if (profile === null) {
      continue;
    }

    try {
      const changes = await prepareIntegrationFiles({
        integration,
        profile,
        environment,
      });

      await applyIntegrationFiles(changes);
      await saveIntegration({
        paths,
        integration: {
          ...integration,
          files: savedRecords(changes),
        },
      });
      refreshed += 1;
    } catch {
      preserved += 1;
    }
  }

  return { refreshed, preserved };
}

export async function integrationHealth(
  options: IntegrationOptions = {},
): Promise<readonly string[]> {
  const paths = options.paths ?? projectPaths;
  const environment = (await readEnvironment(paths))?.phase === "active";
  const lines: string[] = [];

  for (const integration of await readIntegrations(paths)) {
    let status = "installed";

    for (const file of integration.files) {
      try {
        const text = await readLocalText(
          integrationFilePath({ integration, file }),
        );

        if (text === null) {
          status = "missing files";
          break;
        }

        if (
          file.kind === "hooks"
            ? !hasOwnedHooks({ text, integration })
            : fingerprint(
                file.kind === "instructions"
                  ? (managedSection(text) ?? "")
                  : text,
              ) !== file.fingerprint
        ) {
          status = "edited managed content";
          break;
        }
      } catch {
        status = "invalid destination";
        break;
      }
    }

    if (status === "installed") {
      const profile = await compileContext({
        ...options,
        paths,
        cwd: integration.directory,
        scope: integration.scope === "global" ? "global" : "combined",
      });

      if (profile === null) {
        status = "blocked by policy";
      } else {
        const changes = await prepareIntegrationFiles({
          integration,
          profile,
          environment,
        });

        if (changes.some((change) => change.next !== change.previous)) {
          status = "stale";
        }
      }
    }

    lines.push(
      `${integration.agent} (${integration.scope}): ${status}; ${integration.deliveredAt === null ? "hook not observed" : "hook delivery observed"}`,
    );
  }

  return lines;
}
