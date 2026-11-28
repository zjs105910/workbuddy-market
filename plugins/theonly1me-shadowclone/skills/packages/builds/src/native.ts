import path from "node:path";
import type { FileUpdate } from "@shadowclone/changes";
import {
  type BuildContext,
  type BuildDefinition,
  type EnvironmentState,
  planBuildIntegrations,
  renderBuildRouting,
  renderSkillRouting,
  updateManagedSection,
} from "@shadowclone/environment";
import { readLocalText } from "@shadowclone/core";

export async function planBuildRouting(
  options: BuildContext & {
    readonly state: EnvironmentState;
    readonly build: BuildDefinition;
  },
): Promise<{
  readonly state: EnvironmentState;
  readonly updates: readonly FileUpdate[];
}> {
  if (options.build.scope !== "shared") {
    const routing = renderSkillRouting({
      state: options.state,
      scopes: [
        {
          key: "global",
          directory: path.dirname(options.paths.shadowcloneDirectory),
          repository: null,
        },
      ],
    });

    const planned = await planBuildIntegrations({ ...options, routing });

    return { state: options.state, updates: planned.updates };
  }

  const updates: FileUpdate[] = [];
  let state = options.state;

  for (const name of ["AGENTS.md", "CLAUDE.md"]) {
    const filePath = path.join(options.build.directory, name);
    const previous = await readLocalText(filePath);
    const artifact = state.artifacts.find(
      (entry) => entry.filePath === filePath,
    );

    const body =
      name === "CLAUDE.md"
        ? "@AGENTS.md"
        : renderBuildRouting({
            state,
            cwd: options.build.directory,
            sharedOnly: true,
          });

    const changed = updateManagedSection({
      previous,
      expected: artifact?.fingerprint,
      body,
    });

    updates.push({ filePath, previous, next: changed.text });
    state = {
      ...state,
      artifacts: [
        ...state.artifacts.filter((entry) => entry.filePath !== filePath),
        {
          filePath,
          original: artifact ? artifact.original : previous,
          fingerprint: changed.fingerprint,
          kind: "instructions",
          scope: options.build.id,
          name,
          description: "Shared build routing",
          learningKeys: [],
          buildId: options.build.id,
        },
      ],
    };
  }

  return { state, updates };
}
