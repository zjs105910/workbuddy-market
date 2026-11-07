import { learningModelCatalog, type LearningModelChoice } from "@shadowclone/learning";
import type { ProjectPaths } from "@shadowclone/core";
import type { WizardAnswerPrompt } from "./wizard";

export async function chooseLearningModel(options: {
  readonly paths: ProjectPaths;
  readonly answer?: WizardAnswerPrompt;
  readonly writeLine: (line: string) => void;
}): Promise<LearningModelChoice | null> {
  const catalog = await learningModelCatalog(options.paths);
  if (catalog.choices.length === 0) return null;
  options.writeLine("Choose a model configured in your coding harness for learning:");
  for (const [index, choice] of catalog.choices.entries()) options.writeLine(`${index + 1}. ${choice.name}`);
  const answer = await (options.answer ?? prompt)("Learning model number [1]:");
  const number = answer?.trim() ? Number(answer) : 1;
  const choice = Number.isSafeInteger(number) ? catalog.choices[number - 1] : undefined;
  if (!choice) throw new Error("Choose an available harness model number");
  return choice;
}
