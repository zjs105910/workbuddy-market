import type { EngineRunOptions } from "./types";

export async function buildEnginePrompt(options: {
  readonly run: EngineRunOptions;
  readonly outputSchemaInPrompt: boolean;
}): Promise<string> {
  const sections: string[] = [];

  if (options.run.systemPromptFile) {
    sections.push(
      "Follow this shadowclone profile:",
      await Bun.file(options.run.systemPromptFile).text(),
    );
  }

  sections.push("Complete this task:", options.run.prompt);

  if (options.outputSchemaInPrompt && options.run.outputSchema !== undefined) {
    sections.push(
      "Return only JSON matching this schema:",
      JSON.stringify(options.run.outputSchema),
    );
  }

  return sections.join("\n\n");
}
