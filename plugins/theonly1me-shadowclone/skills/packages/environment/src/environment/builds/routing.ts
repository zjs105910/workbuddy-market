import path from "node:path";
import type {
  EnvironmentArtifact,
  EnvironmentState,
} from "../types";

export function renderBuildRouting(options: {
  readonly state: EnvironmentState;
  readonly cwd?: string;
  readonly sharedOnly?: boolean;
  readonly includeGlobal?: boolean;
}): string {
  const builds = options.state.builds.filter((build) =>
    options.sharedOnly
      ? build.scope === "shared" && build.directory === options.cwd
      : (build.scope === "global" && options.includeGlobal !== false) ||
        (options.cwd !== undefined &&
          (options.cwd === build.directory ||
            options.cwd.startsWith(`${build.directory}${path.sep}`))),
  );

  if (builds.length === 0) {
    return "";
  }

  builds.sort(
    (left, right) =>
      Number(left.scope !== "global") - Number(right.scope !== "global") ||
      left.directory.length - right.directory.length,
  );

  const choices: Record<string, boolean> = {};

  for (const build of builds) {
    if (build.scope !== "shared") {
      Object.assign(choices, build.choices);
    }
  }

  const artifacts = new Map<string, EnvironmentArtifact>();

  for (const build of builds) {
    for (const artifact of options.state.artifacts) {
      if (artifact.kind !== "skill" || artifact.buildId !== build.id) {
        continue;
      }

      const enabled =
        build.scope === "shared"
          ? build.choices[artifact.buildEntryId ?? ""]
          : choices[artifact.buildEntryId ?? ""];

      if (
        enabled === false ||
        (!enabled && artifact.buildEntryId !== "build-preferences")
      ) {
        continue;
      }

      const key =
        build.scope === "shared"
          ? `${build.id}:${artifact.name}`
          : artifact.name;
      const previous = artifacts.get(key);

      if (
        !previous ||
        previous.buildId !== build.id ||
        artifact.filePath.includes("/.agents/skills/")
      ) {
        artifacts.set(key, artifact);
      }
    }
  }

  const lines = [
    "## Your agent build",
    "",
    "Follow repository requirements. Repository build choices override personal global choices. Load each selected workflow skill at the moment listed for it. When a selected workflow skill conflicts with the user's own skills or learned baseline rules, follow the user's guidance.",
  ];

  const routedByDescription: string[] = [];

  for (const artifact of artifacts.values()) {
    if (artifact.buildEntryId === "build-preferences") {
      lines.push(
        "Follow the selected working preferences in the shadowclone-build-preferences skill when relevant.",
      );
    } else if (artifact.appliesWhen) {
      lines.push(`- ${artifact.appliesWhen}: ${artifact.name}`);
    } else {
      routedByDescription.push(artifact.name);
    }
  }

  if (routedByDescription.length > 0) {
    lines.push(
      `- when the task matches the skill's own description: ${routedByDescription.join(", ")}`,
    );
  }

  const text = `${lines.join("\n")}\n`;
  const bytes = Buffer.byteLength(text);

  if (bytes > 4096) {
    throw new Error(`Build routing uses ${bytes} of 4096 bytes; equip fewer skills`);
  }

  return text;
}
