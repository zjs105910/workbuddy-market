import path from "node:path";
import type { BuildContext, BuildDefinition } from "./definition";

export function buildDirectories(
  options: BuildContext & { readonly build: BuildDefinition },
): readonly string[] {
  if (options.build.scope === "private") {
    return [
      path.join(
        options.paths.shadowcloneDirectory,
        "builds",
        options.build.id,
        "skills",
      ),
    ];
  }

  const base = options.build.directory;

  return [
    ".agents/skills",
    ".claude/skills",
    ...(options.build.scope === "global" ? [".gemini/config/skills"] : []),
  ].map((relative) => path.join(base, relative));
}
