import { Command } from "commander";
import { z } from "zod";
import { auditStudyCoverage, prepareStudyStage } from "../native/study/phase";
import { assembleSuite, deriveSuite, reportStudy, runStudy, validateStudy } from "../native/study/phases";
import { preparationStages } from "../native/study/prepare";

const common = { protocol: z.literal("preference-study-v1"), yes: z.literal(true) };
const optionsSchema = z.discriminatedUnion("phase", [
  z.strictObject({ ...common, phase: z.literal("prepare"), stage: z.enum(preparationStages), preparationFile: z.string().min(1) }),
  z.strictObject({ ...common, phase: z.literal("coverage"), preparationFile: z.string().min(1), keyFile: z.string().min(1) }),
  z.strictObject({ ...common, phase: z.literal("assemble"), preparationFile: z.string().min(1), keyFile: z.string().min(1), tasksFile: z.string().min(1) }),
  z.strictObject({ ...common, phase: z.literal("derive"), preparationFile: z.string().min(1), suiteFile: z.string().min(1), engine: z.enum(["codex", "claude-code"]), model: z.string().min(1).optional(), effort: z.enum(["medium", "high"]).optional() }),
  z.strictObject({ ...common, phase: z.literal("validate"), suiteFile: z.string().min(1), outputDirectory: z.string().min(1), reportOnly: z.boolean().default(false) }),
  z.strictObject({
    ...common, phase: z.literal("run"), suiteFile: z.string().min(1), outputDirectory: z.string().min(1),
    concurrency: z.coerce.number().int().min(1).max(16).optional(),
    arms: z.string().transform((value) => value.split(",")).optional(),
    tasks: z.string().transform((value) => value.split(",")).optional(),
  }),
  z.strictObject({ ...common, phase: z.literal("report"), suiteFile: z.string().min(1), outputDirectory: z.string().min(1), coverageFile: z.string().min(1), baseReceiptFile: z.string().optional(), candidateSuiteFile: z.string().optional() }),
]);

export function parseStudyArguments(argumentsList: readonly string[]) {
  const command = new Command().exitOverride().allowUnknownOption(false)
    .requiredOption("--protocol <name>")
    .requiredOption("--phase <phase>")
    .option("--stage <stage>")
    .option("--preparation-file <path>")
    .option("--key-file <path>")
    .option("--tasks-file <path>")
    .option("--suite-file <path>")
    .option("--output-directory <path>")
    .option("--coverage-file <path>")
    .option("--concurrency <number>")
    .option("--arms <list>")
    .option("--tasks <list>")
    .option("--base-receipt-file <path>")
    .option("--candidate-suite-file <path>")
    .option("--engine <engine>")
    .option("--model <model>")
    .option("--effort <effort>")
    .option("--report-only")
    .option("-y, --yes");
  command.parse([...argumentsList], { from: "user" });
  return optionsSchema.parse(command.opts());
}

async function execute(options: z.infer<typeof optionsSchema>): Promise<unknown> {
  switch (options.phase) {
    case "prepare": return prepareStudyStage(options);
    case "coverage": return auditStudyCoverage(options);
    case "assemble": return assembleSuite(options);
    case "derive": return deriveSuite(options);
    case "validate": return validateStudy(options);
    case "run": return runStudy(options);
    case "report": return reportStudy(options);
  }
}

export async function studyEvalCommand(argumentsList: readonly string[]): Promise<void> {
  console.log(JSON.stringify(await execute(parseStudyArguments(argumentsList)), null, 2));
}
