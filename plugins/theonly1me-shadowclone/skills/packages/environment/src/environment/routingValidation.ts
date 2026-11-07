import type { ProjectPaths } from "@shadowclone/core";
import { renderSkillRouting } from "./context";
import { learningScopes } from "./scope";
import type { EnvironmentState } from "./types";

export function validateRouting(options: {
  readonly paths: ProjectPaths;
  readonly state: EnvironmentState;
}): void {
  const scopes = learningScopes(options);

  for (const scope of scopes) {
    renderSkillRouting({
      state: options.state,
      scopes: scopes.filter(
        (entry) => entry.key === "global" || entry.key === scope.key,
      ),
    });
  }
}
