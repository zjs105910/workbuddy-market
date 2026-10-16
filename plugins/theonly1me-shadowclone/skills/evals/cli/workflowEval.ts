import { Command } from "commander";
import { z } from "zod";
import { freezeWorkflowTasks, reportWorkflowOutcomes } from "../workflow";

const schema = z.discriminatedUnion("phase", [
  z.strictObject({
    protocol: z.literal("workflow-outcomes-v1"),
    phase: z.literal("freeze"),
    tasksFile: z.string(),
    outputDirectory: z.string(),
  }),
  z.strictObject({
    protocol: z.literal("workflow-outcomes-v1"),
    phase: z.literal("report"),
    suiteFile: z.string(),
    resultsFile: z.string(),
  }),
]);

export async function handleWorkflowEval(
  argumentsList: readonly string[],
): Promise<boolean> {
  if (
    !argumentsList.includes("workflow-outcomes-v1") &&
    !argumentsList.includes("--protocol=workflow-outcomes-v1")
  )
    return false;
  const command = new Command()
    .exitOverride()
    .requiredOption("--protocol <protocol>")
    .requiredOption("--phase <phase>")
    .option("--tasks-file <path>")
    .option("--output-directory <path>")
    .option("--suite-file <path>")
    .option("--results-file <path>");
  command.parse([...argumentsList], { from: "user" });
  const options = schema.parse(command.opts());
  console.log(
    JSON.stringify(
      options.phase === "freeze"
        ? await freezeWorkflowTasks(options)
        : await reportWorkflowOutcomes(options),
      null,
      2,
    ),
  );
  return true;
}
