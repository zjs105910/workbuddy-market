import type { SeedAgentSkill, SeedGuidance, SeedLibrary } from "@shadowclone/skills";

export function optionalSkills(library: SeedLibrary): readonly SeedAgentSkill[] {
  return library.independentSkills.filter((skill) => !skill.alwaysOn);
}

export function alwaysOnSkills(library: SeedLibrary): readonly SeedAgentSkill[] {
  return library.skills.filter((skill) => skill.alwaysOn);
}

function numberedChoices<T extends SeedGuidance>(
  guidance: readonly T[],
): readonly {
  readonly number: string;
  readonly entry: T;
}[] {
  return guidance.map((entry, choiceIndex) => ({
    number: String(choiceIndex + 1),
    entry,
  }));
}

export function parseAxisChoice(options: {
  readonly response: string;
  readonly guidance: readonly SeedGuidance[];
}): SeedGuidance | null {
  const choices = numberedChoices(options.guidance);
  const response = options.response.trim();
  const allowed = new Set(choices.map((choice) => choice.number));

  if (!allowed.has(response)) {
    return null;
  }

  return choices.find((choice) => choice.number === response)?.entry ?? null;
}

export function parseOptionalSkillChoices(options: {
  readonly response: string;
  readonly skills: readonly SeedAgentSkill[];
}): readonly SeedAgentSkill[] | null {
  const response = options.response.trim();

  if (response === "all") {
    return options.skills;
  }

  if (response === "none") {
    return [];
  }

  const choices = numberedChoices(options.skills);
  const allowed = new Set(choices.map((choice) => choice.number));
  const requested = response.split(",").map((value) => value.trim());
  const unique = new Set(requested);

  if (
    requested.length === 0 ||
    requested.length !== unique.size ||
    requested.some((value) => !allowed.has(value))
  ) {
    return null;
  }

  return choices
    .filter((choice) => unique.has(choice.number))
    .map((choice) => choice.entry);
}

export function choiceQuestion<T extends SeedGuidance>(options: {
  readonly heading: string;
  readonly guidance: readonly T[];
  readonly suffix?: string;
}): string {
  return [
    options.heading,
    ...numberedChoices(options.guidance).map(
      (choice) => `  ${choice.number}. ${choice.entry.title}`,
    ),
    ...(options.suffix ? [options.suffix] : []),
  ].join("\n");
}
