import { redactSecrets } from "@shadowclone/redact";
import { handleFixedEval } from "./cli/fixedEval";
import { handleFourSetupEval } from "./cli/fourSetupEval";
import { handleReusableEval } from "./cli/reusableEval";
import { studyEvalCommand } from "./cli/studyEval";
import { handleWorkflowEval } from "./cli/workflowEval";

async function main(rest: string[]): Promise<void> {
  if (await handleReusableEval(rest)) return;
  if (await handleFourSetupEval(rest)) return;
  if (await handleFixedEval(rest)) return;
  if (await handleWorkflowEval(rest)) return;
  await studyEvalCommand(rest);
}

await main(Bun.argv.slice(2)).catch((error: unknown) => {
  const message =
    error instanceof Error ? error.message : "The evaluation could not complete this command";
  console.error(
    message.length <= 1_000
      ? redactSecrets({ text: message })
      : "The evaluation could not complete this command.",
  );
  process.exitCode = 1;
});
