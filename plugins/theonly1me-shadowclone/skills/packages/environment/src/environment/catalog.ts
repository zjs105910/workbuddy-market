import type { EnvironmentArtifact, EnvironmentState } from "./types";

export function publishedSkills(options: {
  readonly state: EnvironmentState;
  readonly scopes: ReadonlySet<string>;
}): readonly EnvironmentArtifact[] {
  const skills = new Map<string, EnvironmentArtifact>();

  for (const artifact of options.state.artifacts) {
    if (
      artifact.kind !== "skill" ||
      artifact.buildId ||
      !options.scopes.has(artifact.scope)
    ) {
      continue;
    }

    const key = `${artifact.scope}/${artifact.name}`;

    if (!skills.has(key) || artifact.filePath.includes("/.agents/skills/")) {
      skills.set(key, artifact);
    }
  }

  return [...skills.values()];
}
