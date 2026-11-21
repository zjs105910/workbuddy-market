import type { ProjectPaths } from "@shadowclone/core";
import { projectPaths } from "@shadowclone/core";
import { applyWizardSelection } from "./wizardApply";
import type { SeedAgentSkill, SeedGuidance, SeedLibrary } from "@shadowclone/skills";
import { loadSeedLibrary } from "@shadowclone/skills";
import { type ConfirmPrompt, promptConfirmation } from "./confirm";

import {
  alwaysOnSkills,
  choiceQuestion,
  optionalSkills,
  parseAxisChoice,
  parseOptionalSkillChoices,
} from "./wizardChoices";

export { parseAxisChoice, parseOptionalSkillChoices } from "./wizardChoices";

export type WizardAnswerPrompt = (
  question: string,
) => string | null | Promise<string | null>;
export type WizardResult = {
  readonly written: boolean;
  readonly selectedGuidanceIds: readonly string[];
};

function promptForAnswer(question: string): string | null {
  return prompt(question);
}

async function chooseAxis(options: {
  readonly axisId: string;
  readonly guidance: readonly SeedGuidance[];
  readonly answer: WizardAnswerPrompt;
  readonly writeLine: (line: string) => void;
}): Promise<SeedGuidance> {
  const question = choiceQuestion({
    heading: `Choose one for ${options.axisId}:`,
    guidance: options.guidance,
  });

  for (;;) {
    const response = await options.answer(question);

    if (response === null) {
      throw new Error("Wizard cancelled before a choice was made");
    }

    const guidance = parseAxisChoice({ response, guidance: options.guidance });

    if (guidance) {
      return guidance;
    }

    options.writeLine("Choose one of the displayed numbers.");
  }
}

async function chooseOptionalSkills(options: {
  readonly skills: readonly SeedAgentSkill[];
  readonly answer: WizardAnswerPrompt;
  readonly writeLine: (line: string) => void;
}): Promise<readonly SeedAgentSkill[]> {
  const question = choiceQuestion({
    heading: "Choose optional skills:",
    guidance: options.skills,
    suffix: "Enter all, none, or comma-separated numbers.",
  });

  for (;;) {
    const response = await options.answer(question);

    if (response === null) {
      throw new Error("Wizard cancelled before optional skills were chosen");
    }

    const skills = parseOptionalSkillChoices({
      response,
      skills: options.skills,
    });

    if (skills !== null) {
      return skills;
    }

    options.writeLine("Choose all, none, or unique displayed numbers.");
  }
}

export async function runWizard(
  options: {
    readonly paths?: ProjectPaths;
    readonly library?: SeedLibrary;
    readonly answer?: WizardAnswerPrompt;
    readonly confirm?: ConfirmPrompt;
    readonly writeLine?: (line: string) => void;
  } = {},
): Promise<WizardResult> {
  const paths = options.paths ?? projectPaths;
  const library = options.library ?? (await loadSeedLibrary());
  const answer = options.answer ?? promptForAnswer;
  const confirm = options.confirm ?? promptConfirmation;
  const writeLine = options.writeLine ?? ((line) => console.log(line));
  const selected: SeedGuidance[] = [];

  for (const axis of library.axes) {
    selected.push(
      await chooseAxis({
        axisId: axis.id,
        guidance: axis.guidance,
        answer,
        writeLine,
      }),
    );
  }

  selected.push(
    ...(await chooseOptionalSkills({
      skills: optionalSkills(library),
      answer,
      writeLine,
    })),
  );
  writeLine("Selected preferences and skills:");

  for (const entry of selected) {
    writeLine(`  ${entry.title}`);
  }

  const alwaysOn = alwaysOnSkills(library);

  if (alwaysOn.length > 0) {
    writeLine("Always included:");

    for (const entry of alwaysOn) {
      writeLine(`  ${entry.title}`);
    }
  }

  const selectedGuidanceIds = selected.map((entry) => entry.id);

  if (!(await confirm("Install these preferences and skills?"))) {
    writeLine("Build unchanged.");

    return { written: false, selectedGuidanceIds };
  }

  await applyWizardSelection({
    paths,
    library,
    selected: [...selected, ...alwaysOn],
  });

  writeLine(
    "Applied your selected preferences and skills to native agent guidance.",
  );

  return { written: true, selectedGuidanceIds };
}
