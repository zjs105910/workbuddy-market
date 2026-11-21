import { type CaseDefinition, caseSchema } from "../scaffold/definition";
import { baseMovedConflict, botPushedToBranch } from "./branches";
import { flakyCiAndPolicy, realCiFailure } from "./ci";
import { botNoiseAndBug, humanScopeRequest, reviewAfterPush, reviewAfterReady } from "./comments";
import { newFeatureTemplate } from "./feature";
import { approvedButBlocking, intendedBehavior, notForYou, suggestionIsABug } from "./judgment";
import { stackFixInParent, stackRestackConflict } from "./stacks";

export const testCaseIds: readonly string[] = [
  "approved-but-blocking",
  "bot-noise-and-bug",
  "bot-pushed-to-branch",
  "flaky-ci-and-policy",
  "stack-restack-conflict",
];

const definitions: readonly CaseDefinition[] = [
  newFeatureTemplate,
  flakyCiAndPolicy,
  realCiFailure,
  botNoiseAndBug,
  humanScopeRequest,
  reviewAfterPush,
  reviewAfterReady,
  baseMovedConflict,
  stackRestackConflict,
  stackFixInParent,
  botPushedToBranch,
  approvedButBlocking,
  suggestionIsABug,
  intendedBehavior,
  notForYou,
];

export const cases: readonly CaseDefinition[] = definitions.map((definition) =>
  caseSchema.parse({ ...definition, split: testCaseIds.includes(definition.id) ? "test" : "train" }),
);

export function caseById(id: string): CaseDefinition {
  const found = cases.find((definition) => definition.id === id);

  if (!found) {
    throw new Error(`Unknown case ${id}`);
  }

  return found;
}
