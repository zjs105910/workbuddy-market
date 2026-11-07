import { customDocument } from "./selection";
import type { BuildItem } from "./types";
import type { BuildInput } from "@shadowclone/environment";

export function authoredBuildSkills(options: {
  readonly input: BuildInput;
  readonly selected: readonly BuildItem[];
}): readonly BuildItem[] {
  const preferences = options.selected.filter(
    (item) => item.kind === "preference",
  );

  const baseline = preferences
    .map(
      (item) =>
        `## ${item.title}\n\n${options.input.edits[item.id] ?? item.text}`,
    )
    .join("\n\n");

  if (Buffer.byteLength(baseline) > 4096) {
    throw new Error(
      "Universal preferences exceed 4 KiB; move detailed procedures into a skill",
    );
  }

  const authored: BuildItem[] = [
    ...options.selected.filter(
      (item) =>
        item.kind === "skill" &&
        !options.input.custom.some(
          (skill) => item.id === `custom:${skill.name}`,
        ),
    ),
    ...options.input.custom
      .filter(
        (skill) => options.input.choices[`custom:${skill.name}`] !== false,
      )
      .map(
        (skill): BuildItem => ({
          id: `custom:${skill.name}`,
          name: skill.name,
          title: skill.name,
          description: skill.description,
          text: customDocument(skill),
          kind: "skill",
          category: null,
          section: null,
          axis: null,
          alwaysOn: false,
          owner: "managed",
        }),
      ),
  ];

  if (preferences.length > 0) {
    const description =
      "Read before acting for the selected working preferences.";

    authored.push({
      id: "build-preferences",
      name: "shadowclone-build-preferences",
      title: "Working preferences",
      description,
      text: customDocument({
        name: "shadowclone-build-preferences",
        description,
        body: baseline,
      }),
      kind: "skill",
      category: "working-preferences",
      section: "workflow",
      axis: null,
      alwaysOn: false,
      owner: "managed",
    });
  }

  const names = new Set(authored.map((item) => item.name));

  if (names.size !== authored.length) {
    throw new Error(
      "Two selected skills use the same name; give the custom skill a different name",
    );
  }

  return authored;
}
