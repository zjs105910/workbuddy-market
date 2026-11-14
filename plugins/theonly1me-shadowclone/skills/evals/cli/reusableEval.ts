import { Command, CommanderError } from "commander";
import { z } from "zod";
import {
  writeCaseReview,
  approveCaseReview,
  prepareReusableEnvironments,
  authorizePreparations,
  learnReusableEnvironments,
  prepareReusableSuite,
  authorizeReusableRun,
  validateReusableSuite,
  validateOfflineSandbox,
  executeReusableSuite,
  reportReusableSuite,
  compareReusableRuns,
  reviewLearning,
  reuseReusablePreparations,
} from "../fixed/reusable";

const common = { protocol: z.literal("preference-respect-v3"), json: z.boolean().optional() };
const host = {
  engine: z.enum(["codex", "claude-code"]),
  model: z.string(),
  effort: z.enum(["medium", "high"]),
};
const schema = z.discriminatedUnion("phase", [
  z.strictObject({
    ...common,
    phase: z.literal("review"),
    bundleFile: z.string(),
    reviewFile: z.string(),
  }),
  z.strictObject({
    ...common,
    phase: z.literal("approve-review"),
    reviewFile: z.string(),
    fingerprint: z.string(),
  }),
  z.strictObject({
    ...common,
    phase: z.literal("prepare-environments"),
    bundleFile: z.string(),
    reviewFile: z.string(),
    outputDirectory: z.string(),
    model: z.string(),
    effort: z.enum(["medium", "high"]),
    maximumCalls: z.coerce.number().int().min(1).max(16).default(16),
  }),
  z.strictObject({
    ...common,
    phase: z.literal("approve-learning"),
    preparationFile: z.string(),
    fingerprint: z.string(),
  }),
  z.strictObject({
    ...common,
    phase: z.literal("learn"),
    preparationFile: z.string(),
    scopeFile: z.string(),
    yes: z.literal(true),
  }),
  z.strictObject({
    ...common,
    phase: z.literal("review-learning"),
    environmentsFile: z.string(),
    assessmentFile: z.string(),
  }),
  z.strictObject({
    ...common,
    phase: z.literal("reuse-learning"),
    sourceFile: z.string(),
    preparationFile: z.string(),
  }),
  z.strictObject({
    ...common,
    ...host,
    phase: z.literal("prepare"),
    preparationFile: z.string(),
    environmentsFile: z.string().optional(),
    outputDirectory: z.string(),
    experiment: z.enum(["learning", "routing"]),
    runPhase: z.enum(["preflight", "development", "qualification"]),
  }),
  z.strictObject({
    ...common,
    phase: z.literal("approve-run"),
    suiteFile: z.string(),
    fingerprint: z.string(),
  }),
  z.strictObject({ ...common, phase: z.literal("validate"), suiteFile: z.string() }),
  z.strictObject({ ...common, phase: z.literal("validate-sandbox"), outputDirectory: z.string() }),
  z.strictObject({
    ...common,
    phase: z.literal("run"),
    suiteFile: z.string(),
    scopeFile: z.string(),
    yes: z.literal(true),
  }),
  z.strictObject({ ...common, phase: z.literal("report"), suiteFile: z.string() }),
  z.strictObject({
    ...common,
    phase: z.literal("compare"),
    baselineFile: z.string(),
    candidateFile: z.string(),
  }),
]);

export function parseReusableArguments(argumentsList: readonly string[]) {
  const command = new Command()
    .name("bun run eval")
    .exitOverride()
    .description(
      "Frozen five-setup learning benchmark and independent 20-skill routing experiment. Offline phases make no authenticated calls.",
    )
    .requiredOption("--protocol <protocol>")
    .requiredOption(
      "--phase <phase>",
      "review, approve-review, prepare-environments, approve-learning, learn, review-learning, reuse-learning, prepare, approve-run, validate, validate-sandbox, run, report, compare",
    )
    .option("--bundle-file <path>")
    .option("--review-file <path>")
    .option("--preparation-file <path>")
    .option("--environments-file <path>")
    .option("--suite-file <path>")
    .option("--scope-file <path>")
    .option("--fingerprint <hash>")
    .option("--assessment-file <path>")
    .option("--source-file <path>")
    .option("--output-directory <path>", "new private directory outside repositories")
    .option("--engine <engine>", "codex or claude-code")
    .option("--model <model>")
    .option("--effort <level>", "medium or high")
    .option("--maximum-calls <count>", "per-preparation learning cap, 1 to 16; three preparations")
    .option("--experiment <experiment>", "learning or routing")
    .option("--run-phase <phase>", "preflight, development, or qualification")
    .option("--baseline-file <path>")
    .option("--candidate-file <path>")
    .option("--json")
    .option("--yes", "execute only the supplied newly approved exact scope");
  try {
    command.parse([...argumentsList], { from: "user" });
  } catch (error) {
    if (error instanceof CommanderError && error.code === "commander.helpDisplayed") return null;
    throw error;
  }
  return schema.parse(command.opts());
}

export async function handleReusableEval(argumentsList: readonly string[]) {
  if (
    !argumentsList.includes("preference-respect-v3") &&
    !argumentsList.includes("--protocol=preference-respect-v3")
  )
    return false;
  const options = parseReusableArguments(argumentsList);
  if (!options) return true;
  let result: unknown;
  switch (options.phase) {
    case "review":
      result = await writeCaseReview(options);
      break;
    case "approve-review":
      result = await approveCaseReview(options);
      break;
    case "prepare-environments":
      result = await prepareReusableEnvironments({
        ...options,
        directory: options.outputDirectory,
      });
      break;
    case "approve-learning":
      result = await authorizePreparations(options);
      break;
    case "learn":
      result = await learnReusableEnvironments(options);
      break;
    case "review-learning":
      result = await reviewLearning(options);
      break;
    case "reuse-learning":
      result = await reuseReusablePreparations(options);
      break;
    case "prepare":
      result = await prepareReusableSuite({
        ...options,
        directory: options.outputDirectory,
        phase: options.runPhase,
      });
      break;
    case "approve-run":
      result = await authorizeReusableRun(options);
      break;
    case "validate":
      result = await validateReusableSuite(options.suiteFile);
      break;
    case "validate-sandbox":
      result = await validateOfflineSandbox(options.outputDirectory);
      break;
    case "run":
      await executeReusableSuite(options);
      result = await reportReusableSuite(options.suiteFile);
      break;
    case "report":
      result = await reportReusableSuite(options.suiteFile);
      break;
    case "compare":
      result = await compareReusableRuns(options);
      break;
  }
  console.log(JSON.stringify(result, null, 2));
  if (
    typeof result === "object" &&
    result !== null &&
    (("passed" in result && result.passed === false) ||
      ("completed" in result && result.completed === false) ||
      ("status" in result && result.status === "incomplete"))
  )
    process.exitCode = 1;
  return true;
}
