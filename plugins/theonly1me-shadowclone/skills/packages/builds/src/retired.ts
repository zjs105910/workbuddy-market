import type { BuildDefinition } from "@shadowclone/environment";

export type RetiredSkill = {
  readonly replacement: string;
  readonly defaultPreference?: string;
};

export const retiredBundledSkills: ReadonlyMap<string, RetiredSkill> = new Map([
  ["prove-regression-tests", { replacement: "tests-that-catch-bugs" }],
  [
    "testing-first",
    {
      replacement: "tests-that-catch-bugs",
      defaultPreference: "Write the failing test before the production change.",
    },
  ],
  ["testing-risk-based", { replacement: "tests-that-catch-bugs" }],
]);

export type RetiredSkillChange =
  | {
      readonly kind: "replaced";
      readonly build: BuildDefinition;
      readonly retired: readonly string[];
      readonly replacement: string;
      readonly preferences: readonly { readonly retired: string; readonly text: string }[];
    }
  | {
      readonly kind: "kept";
      readonly build: BuildDefinition;
      readonly retired: string;
      readonly replacement: string;
      readonly filePath: string | null;
    }
  | {
      readonly kind: "failed";
      readonly build: BuildDefinition;
      readonly retired: readonly string[];
      readonly replacements: readonly string[];
      readonly reason: string;
    };

export function activeRetirements(options: {
  readonly retired: ReadonlyMap<string, RetiredSkill>;
  readonly libraryIds: ReadonlySet<string>;
}): ReadonlyMap<string, RetiredSkill> {
  return new Map(
    [...options.retired].filter(
      ([id, entry]) => !options.libraryIds.has(id) && options.libraryIds.has(entry.replacement),
    ),
  );
}

export function buildLabel(build: BuildDefinition): string {
  if (build.scope === "global") {
    return "your global build";
  }

  return build.scope === "shared"
    ? `the shared build for ${build.directory}`
    : `your private build for ${build.directory}`;
}

function listed(names: readonly string[]): string {
  return names.length < 2
    ? names.join("")
    : `${names.slice(0, -1).join(", ")} and ${names.at(-1) ?? ""}`;
}

function preferenceLine(options: {
  readonly build: BuildDefinition;
  readonly retired: string;
  readonly text: string;
}): string {
  return options.build.scope === "global"
    ? `To keep the ${options.retired} default, run: shadowclone remember --global "${options.text}"`
    : `To keep the ${options.retired} default in ${options.build.directory}, run this command there: shadowclone remember --repo "${options.text}"`;
}

export function renderRetiredSkillChanges(
  changes: readonly RetiredSkillChange[],
): readonly string[] {
  return changes.flatMap((change) => {
    if (change.kind === "failed") {
      return [
        change.replacements.length > 0
          ? `Could not replace ${listed(change.retired)} with ${listed(change.replacements)} in ${buildLabel(change.build)}: ${change.reason}`
          : `Could not remove ${listed(change.retired)} from ${buildLabel(change.build)}: ${change.reason}`,
      ];
    }

    if (change.kind === "kept") {
      const kept =
        change.filePath === null
          ? `${change.retired} in ${buildLabel(change.build)}, because you changed it in the build editor`
          : `your edited copy of ${change.retired} at ${change.filePath}`;

      return [
        `Kept ${kept}. It is no longer bundled. To replace it with ${change.replacement}, use shadowclone wizard.`,
      ];
    }

    return [
      `Replaced ${listed(change.retired)} with ${change.replacement} in ${buildLabel(change.build)}.`,
      ...change.preferences.map((preference) =>
        preferenceLine({ build: change.build, ...preference }),
      ),
    ];
  });
}
