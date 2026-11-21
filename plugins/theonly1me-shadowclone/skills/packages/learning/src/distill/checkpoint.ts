import path from "node:path";
import { ownedWrite } from "@shadowclone/core";
import {
  parseReconciliationOutput,
  reconciliationOutputSchema,
  type ReconciliationOutput,
} from "./reconcile";

export const reconciliationLearnerVersion = "steering-reconciliation-v2";

export function checkpointId(options: {
  readonly prompt: string;
  readonly outputSchema?: unknown;
  readonly learnerVersion?: string;
}): string {
  const identity = JSON.stringify({
    prompt: options.prompt,
    outputSchema: options.outputSchema ?? reconciliationOutputSchema,
    learnerVersion: options.learnerVersion ?? reconciliationLearnerVersion,
  });

  return new Bun.CryptoHasher("sha256")
    .update(identity)
    .digest("hex")
    .slice(0, 24);
}

function checkpointPath(options: {
  readonly checkpointDirectory: string;
  readonly prompt: string;
}): string {
  return path.join(
    options.checkpointDirectory,
    `${checkpointId({ prompt: options.prompt })}.json`,
  );
}

export async function readCheckpoint(options: {
  readonly checkpointDirectory: string;
  readonly prompt: string;
}): Promise<ReconciliationOutput | null> {
  const file = Bun.file(checkpointPath(options));

  if (!(await file.exists())) {
    return null;
  }

  try {
    return parseReconciliationOutput(await file.json());
  } catch {
    return null;
  }
}

export async function writeCheckpoint(options: {
  readonly checkpointDirectory: string;
  readonly prompt: string;
  readonly output: ReconciliationOutput;
}): Promise<void> {
  await ownedWrite({
    path: checkpointPath(options),
    content: `${JSON.stringify(options.output, null, 2)}\n`,
  });
}
