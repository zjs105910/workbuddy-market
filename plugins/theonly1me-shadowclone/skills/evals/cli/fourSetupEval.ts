import { Command, CommanderError } from "commander";
import { z } from "zod";
import { prepareWorkflowEnvironments, learnWorkflowEnvironments, prepareWorkflowSuite, validateWorkflowSuite, runWorkflowSuite, reportWorkflowSuite, compareWorkflowRuns } from "../fixed/workflow";
import { workflowReportSchema } from "../fixed/workflow/report";
import { workflowReportText } from "../fixed/workflow/display";

const common = { protocol: z.literal("preference-respect-v2"), json: z.boolean().optional() };
const model = { engine: z.enum(["codex", "claude-code"]), model: z.string().min(1), effort: z.enum(["medium", "high"]) };
const schema = z.discriminatedUnion("phase", [
  z.strictObject({ ...common, ...model, phase: z.literal("prepare-environments"), outputDirectory: z.string(), maximumCalls: z.coerce.number().int().min(1).max(16).default(16) }),
  z.strictObject({ ...common, phase: z.literal("learn"), preparationFile: z.string(), yes: z.literal(true) }),
  z.strictObject({ ...common, ...model, phase: z.literal("prepare"), environmentsFile: z.string(), outputDirectory: z.string(), repetitions: z.coerce.number().int().min(1).max(5).default(3) }),
  z.strictObject({ ...common, phase: z.literal("validate"), suiteFile: z.string() }),
  z.strictObject({ ...common, phase: z.literal("run"), suiteFile: z.string(), yes: z.literal(true) }),
  z.strictObject({ ...common, phase: z.literal("report"), suiteFile: z.string() }),
  z.strictObject({ ...common, phase: z.literal("compare"), baselineFile: z.string(), candidateFile: z.string() }),
]);

export function parseFourSetupArguments(argumentsList: readonly string[]) {
  const command = new Command().name("bun run eval").exitOverride()
    .description("Compare bare, existing skills, routing, and actual learning from fixed synthetic corrections.")
    .requiredOption("--protocol <protocol>").requiredOption("--phase <phase>", "prepare-environments, learn, prepare, validate, run, report, compare")
    .option("--engine <engine>", "codex or claude-code").option("--model <model>").option("--effort <level>", "medium or high")
    .option("--output-directory <path>", "new private directory outside repositories").option("--maximum-calls <count>", "learning cap, at most 16")
    .option("--repetitions <count>", "scored repetitions, 1 to 5; defaults to 3").option("--preparation-file <path>")
    .option("--environments-file <path>").option("--suite-file <path>").option("--baseline-file <path>").option("--candidate-file <path>")
    .option("--json").option("--yes", "authorize this frozen phase's native calls and disposable workspace writes");
  try { command.parse([...argumentsList], { from: "user" }); }
  catch (error) {
    if (error instanceof CommanderError && error.code === "commander.helpDisplayed") return null;
    throw error;
  }
  return schema.parse(command.opts());
}

export async function handleFourSetupEval(argumentsList: readonly string[]) {
  if (!argumentsList.includes("preference-respect-v2") && !argumentsList.includes("--protocol=preference-respect-v2")) return false;
  const options = parseFourSetupArguments(argumentsList);
  if (options === null) return true;
  let result: unknown;
  switch (options.phase) {
    case "prepare-environments": result = { preparationFile: await prepareWorkflowEnvironments({ ...options, directory: options.outputDirectory }) }; break;
    case "learn": result = await learnWorkflowEnvironments(options); break;
    case "prepare": result = { suiteFile: await prepareWorkflowSuite({ ...options, directory: options.outputDirectory }) }; break;
    case "validate": result = await validateWorkflowSuite(options.suiteFile); break;
    case "run": result = await runWorkflowSuite(options); break;
    case "report": result = await reportWorkflowSuite(options.suiteFile); break;
    case "compare": result = await compareWorkflowRuns(options); break;
  }
  console.log((options.phase === "run" || options.phase === "report") && !options.json ? workflowReportText(workflowReportSchema.parse(result)) : JSON.stringify(result, null, 2));
  if (typeof result === "object" && result !== null && ("passed" in result && result.passed === false || "status" in result && result.status === "incomplete" ||
    "learning" in result && typeof result.learning === "object" && result.learning !== null && "outcome" in result.learning && result.learning.outcome === "incomplete")) process.exitCode = 1;
  return true;
}
