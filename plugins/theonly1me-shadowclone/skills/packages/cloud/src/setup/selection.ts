import path from "node:path";
import {
  type BuildContext,
  learningScopes,
  publishedSkills,
  readRedactedEnvironment,
} from "@shadowclone/environment";
import { resolveRepository, type GitRemoteReader } from "@shadowclone/sessions";

export async function setupSelection(
  context: BuildContext & {
    readonly readRemote?: GitRemoteReader;
  },
) {
  const repository = await resolveRepository({
    cwd: context.cwd,
    enabled: true,
    readRemote: context.readRemote,
  });
  const state = await readRedactedEnvironment(context.paths);
  const repositoryName = repository?.id.startsWith("github.com/")
    ? repository.id.slice("github.com/".length)
    : null;

  if (state?.phase !== "active" || !repository) {
    return { repository: repositoryName, skills: [] };
  }

  const scopes = learningScopes({ paths: context.paths, state }).filter(
    (scope) =>
      scope.repository === null ||
      (scope.repository.originDirectory === repository.origin.directoryName &&
        scope.repository.repositoryName === repository.profileFileName &&
        (context.cwd === scope.directory ||
          context.cwd.startsWith(`${scope.directory}${path.sep}`))),
  );
  const personalBuilds = new Set(
    state.builds.filter((build) => build.scope === "global").map((build) => build.id),
  );
  const names = new Set([
    "shadowclone-work",
    ...publishedSkills({ state, scopes: new Set(scopes.map((scope) => scope.key)) }).map(
      (skill) => skill.name,
    ),
    ...state.artifacts
      .filter((artifact) => artifact.kind === "skill" && personalBuilds.has(artifact.buildId ?? ""))
      .map((artifact) => artifact.name),
  ]);

  return { repository: repositoryName, skills: [...names].sort() };
}
