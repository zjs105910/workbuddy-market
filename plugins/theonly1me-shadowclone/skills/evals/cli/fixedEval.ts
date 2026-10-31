import { Command, CommanderError } from "commander";
import { z } from "zod";
import { authorizeFixedRun, compareFixedRuns, prepareFixedSuite, reportFixedSuite, runFixedSuite, validateFixedSuite } from "../fixed";
import { fixedReportSchema } from "../fixed/report";
import { fixedReportText } from "../fixed/display";

const common = { protocol: z.literal("preference-respect-v1"), json: z.boolean().optional() };

const schema = z.discriminatedUnion("phase", [
  z.strictObject({ phase: z.literal("prepare"), ...common,
    outputDirectory: z.string(), engine: z.enum(["codex", "claude-code"]), model: z.string().min(1), effort: z.enum(["medium", "high"]),
    repetitions: z.coerce.number().int().min(1).max(5).default(3) }),
  z.strictObject({ phase: z.literal("validate"), ...common, suiteFile: z.string() }),
  z.strictObject({ phase: z.literal("run"), ...common, suiteFile: z.string(), yes: z.literal(true) }),
  z.strictObject({ phase: z.literal("report"), ...common, suiteFile: z.string() }),
  z.strictObject({ phase: z.literal("compare"), ...common, baselineFile: z.string(), candidateFile: z.string() }),
]);

export function parseFixedArguments(argumentsList: readonly string[]) {
  const command = new Command()
    .name("bun run eval")
    .exitOverride()
    .description("Run fixed synthetic tasks against bare, handwritten profile, and Shadowclone skill delivery. No learning is required.")
    .requiredOption("--protocol <protocol>")
    .requiredOption("--phase <phase>", "prepare, validate, run, report, or compare")
    .option("--output-directory <path>", "new private run directory outside any repository")
    .option("--engine <engine>", "codex or claude-code")
    .option("--model <model>")
    .option("--effort <level>", "medium or high")
    .option("--repetitions <count>", "1 to 5; prepare defaults to 3")
    .option("--suite-file <path>")
    .option("--baseline-file <path>")
    .option("--candidate-file <path>")
    .option("--json", "print the report as JSON; run progress still precedes it")
    .option("--yes", "authorize the frozen native calls and disposable Git workspace writes");
  try {
    command.parse([...argumentsList], { from: "user" });
  } catch (error) {
    if (error instanceof CommanderError && error.code === "commander.helpDisplayed") return null;
    throw error;
  }
  return schema.parse(command.opts());
}

export async function handleFixedEval(argumentsList: readonly string[]): Promise<boolean> {
  if (!argumentsList.includes("preference-respect-v1") && !argumentsList.includes("--protocol=preference-respect-v1")) return false;
  const options = parseFixedArguments(argumentsList);
  if (options === null) return true;
  let result: unknown;
  switch (options.phase) {
    case "prepare":
      await authorizeFixedRun({ engine: options.engine });
      result = { suiteFile: await prepareFixedSuite({ directory: options.outputDirectory, engine: options.engine, model: options.model, effort: options.effort, repetitions: options.repetitions }) };
      break;
    case "validate": result = await validateFixedSuite(options.suiteFile); break;
    case "run": result = await runFixedSuite(options); break;
    case "report": result = await reportFixedSuite(options.suiteFile); break;
    case "compare": result = await compareFixedRuns(options); break;
  }
  console.log((options.phase === "run" || options.phase === "report") && !options.json ? fixedReportText(fixedReportSchema.parse(result)) : JSON.stringify(result, null, 2));
  if (options.phase === "validate" && typeof result === "object" && result !== null && "passed" in result && result.passed === false) process.exitCode = 1;
  if ((options.phase === "run" || options.phase === "report") && typeof result === "object" && result !== null && "status" in result && result.status === "incomplete") process.exitCode = 1;
  return true;
}
