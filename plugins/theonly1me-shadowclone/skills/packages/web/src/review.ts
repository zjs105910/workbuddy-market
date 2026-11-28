import path from "node:path";
import type { BuildPlan } from "@shadowclone/builds";
import type { BuildPreview } from "./protocol";
import type { BuildContext } from "@shadowclone/environment";

export function reviewBuild(
  options: BuildContext & {
    readonly plan: BuildPlan;
    readonly id: string;
  },
): BuildPreview {
  const home = path.dirname(options.paths.shadowcloneDirectory);

  return {
    id: options.id,
    warnings: [...options.plan.warnings],
    changes: options.plan.updates.map((update) => {
      const internal =
        update.filePath.startsWith(
          `${options.paths.shadowcloneDirectory}${path.sep}`,
        ) && !update.filePath.endsWith("SKILL.md");
      const displayPath = update.filePath.startsWith(`${home}${path.sep}`)
        ? `~/${path.relative(home, update.filePath)}`
        : path.relative(options.cwd, update.filePath);
      const binary = update.encoding === "base64";

      return {
        path: displayPath,
        before: internal || binary ? null : (update.previous ?? null),
        after: internal || binary ? null : update.next,
        internal: internal || binary,
      };
    }),
  };
}
