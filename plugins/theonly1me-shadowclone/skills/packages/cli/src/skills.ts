import { loadSeedLibrary, type SeedLibrary } from "@shadowclone/skills";
import { alwaysOnSkills, optionalSkills } from "./wizardChoices";

function appendAxes(options: {
  readonly lines: string[];
  readonly heading: string;
  readonly axes: SeedLibrary["axes"];
}): void {
  options.lines.push(options.heading);

  for (const axis of options.axes) {
    options.lines.push(`  ${axis.id}`);

    for (const entry of axis.guidance) {
      options.lines.push(`    ${entry.id}: ${entry.title}`);
    }
  }
}

export function renderSeedLibrary(library: SeedLibrary): readonly string[] {
  const preferenceAxes = library.axes.filter((axis) =>
    axis.guidance.every((entry) => entry.kind === "preference"),
  );
  const skillAxes = library.axes.filter((axis) =>
    axis.guidance.every((entry) => entry.kind === "skill"),
  );
  const lines: string[] = [];

  appendAxes({
    lines,
    heading: "Profile preference axes",
    axes: preferenceAxes,
  });
  lines.push("");
  appendAxes({ lines, heading: "Skill axes", axes: skillAxes });
  lines.push("", "Optional skills");

  for (const skill of optionalSkills(library)) {
    lines.push(`  ${skill.id}: ${skill.title}`);
  }

  lines.push("", "Always on skills");

  for (const skill of alwaysOnSkills(library)) {
    lines.push(`  ${skill.id}: ${skill.title}`);
  }

  return lines;
}

export async function listSeedGuidance(): Promise<void> {
  const library = await loadSeedLibrary();

  for (const line of renderSeedLibrary(library)) {
    console.log(line);
  }
}
