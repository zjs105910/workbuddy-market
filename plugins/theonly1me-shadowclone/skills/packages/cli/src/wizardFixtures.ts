import type { SeedLibrary } from "@shadowclone/skills";
import { optionalSkills } from "./wizardChoices";

export function wizardAnswers(options: {
  readonly library: SeedLibrary;
  readonly skill: string;
}): readonly string[] {
  const number = optionalSkills(options.library).findIndex((entry) => entry.id === options.skill);

  if (number < 0) {
    throw new Error(`${options.skill} is not an optional bundled skill`);
  }

  return [...options.library.axes.map(() => "1"), String(number + 1)];
}
