import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { type CopiedCase, copiedCaseSchema } from "../copy";
import { inBatches } from "../github";
import { type PreparedCase, readPreparedCases } from "../prepare";
import { runGreptile } from "./greptile";
import { localRunner } from "./local";
import { runOpenqodex } from "./openqodex";
import { runShadowclone } from "./shadowclone";
import type { ArmName, ArmRun, ArmRunner, LocalArmName } from "./types";

export { armNames, localArmNames, type ArmName, type ArmRun, type LocalArmName } from "./types";

const parallelRuns: Readonly<Record<ArmName, number>> = {
  shadowclone: 10,
  greptile: 10,
  openqodex: 3,
  "shadowclone-branch": 4,
  "openqodex-branch": 3,
  "shadowclone-upstream": 4,
  "openqodex-upstream": 3,
};

function runnerFor(options: { readonly arm: ArmName; readonly checkout: string; readonly model: string }): ArmRunner {
  if (options.arm === "shadowclone") {
    return runShadowclone;
  }

  return options.arm === "greptile" ? runGreptile : runOpenqodex({ checkout: options.checkout, model: options.model });
}

async function runCases<Entry extends { readonly id: string }>(options: {
  readonly arm: ArmName;
  readonly runs: string;
  readonly cases: readonly Entry[];
  readonly only?: readonly string[];
  readonly run: (options: { readonly entry: Entry; readonly directory: string }) => Promise<ArmRun>;
}): Promise<readonly ArmRun[]> {
  return inBatches({
    items: options.cases.filter((entry) => options.only === undefined || options.only.includes(entry.id)),
    size: parallelRuns[options.arm],
    work: async (entry: Entry) => {
      const directory = path.join(options.runs, options.arm, entry.id);

      mkdirSync(directory, { recursive: true });

      const run = await options.run({ entry, directory });

      writeFileSync(path.join(directory, "run.json"), JSON.stringify(run, null, 2));
      console.error(`${options.arm} ${entry.id}: ${run.status} (${run.detail})`);
      return run;
    },
  });
}

export async function runArm(options: {
  readonly arm: ArmName;
  readonly mined: string;
  readonly runs: string;
  readonly evalRepository: string;
  readonly checkout: string;
  readonly model: string;
  readonly only?: readonly string[];
}): Promise<readonly ArmRun[]> {
  const copied = z.array(copiedCaseSchema).parse(JSON.parse(readFileSync(path.join(options.mined, "copied.json"), "utf8")));
  const runner = runnerFor(options);

  return runCases<CopiedCase>({ ...options, cases: copied, run: ({ entry, directory }) => runner({ entry, evalRepository: options.evalRepository, directory }) });
}

export async function runLocalArm(options: {
  readonly arm: LocalArmName;
  readonly mined: string;
  readonly runs: string;
  readonly clone: string;
  readonly model: string;
  readonly only?: readonly string[];
}): Promise<readonly ArmRun[]> {
  return runCases<PreparedCase>({ ...options, cases: readPreparedCases(options.mined), run: localRunner(options) });
}
