import path from "node:path";
import { fingerprint, readLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { materializeSnapshot } from "@shadowclone/redact";
import type { DiscoveredSkill } from "@shadowclone/skills";
import type { LearningRoute } from "./planner";
import type { LearningScope } from "@shadowclone/environment";

export async function resolveLearningTarget(options: {
  readonly paths: ProjectPaths;
  readonly skills: readonly DiscoveredSkill[];
  readonly scope: LearningScope;
  readonly route: LearningRoute;
}) {
  const { route } = options;

  const selected =
    options.skills.find(({ id }) => id === route.skillId) ?? null;
  const companion = selected?.root.owner === "third-party";

  const name =
    route.destination === "baseline"
      ? "shadowclone-baseline"
      : companion
        ? `shadowclone-local-${selected.id.slice(0, 20)}`
        : (selected?.name ?? route.name);

  const target =
    selected && !companion
      ? path.join(selected.root.directory, selected.relativePath)
      : path.join(options.scope.directory, ".agents/skills", name, "SKILL.md");

  const rawOriginal =
    selected && !companion ? selected.raw : await readLocalText(target);

  const snapshot =
    selected && !companion
      ? null
      : await materializeSnapshot({
          filePath: target,
          roots: [path.join(options.scope.directory, ".agents/skills")],
          maximumBytes: 48_000,
          parse: () => null,
        });

  const original =
    selected && !companion ? selected.redacted : (snapshot?.redacted ?? null);

  const targetDetails = { name, target, rawOriginal, original };

  return selected && companion
    ? { ...targetDetails, selected, companion: true as const }
    : { ...targetDetails, selected, companion: false as const };
}

export function existingLearningSkill(
  options: Awaited<ReturnType<typeof resolveLearningTarget>> & {
    readonly scope: LearningScope;
    readonly route: LearningRoute;
  },
): DiscoveredSkill | null {
  const { selected, companion, name, target, rawOriginal, original, route } =
    options;

  const existing =
    selected && !companion
      ? selected
      : rawOriginal === null
        ? null
        : {
            id: fingerprint(target),
            root: {
              id: fingerprint(path.dirname(path.dirname(target))),
              directory: path.dirname(path.dirname(target)),
              cwd: options.scope.directory,
              scope:
                options.scope.repository === null
                  ? ("global" as const)
                  : ("repository" as const),
              owner: "user" as const,
              destination: path.dirname(path.dirname(target)),
              enabled: true,
            },
            relativePath: `${name}/SKILL.md`,
            raw: rawOriginal,
            redacted: original ?? "",
            fingerprint: fingerprint(rawOriginal),
            name,
            description: route.description,
            body: original ?? "",
          };

  return existing;
}
