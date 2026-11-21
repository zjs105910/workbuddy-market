import type { DiffFile } from "../collect";
import { findRuleHits } from "./apply";
import { javascriptRules } from "./javascript";
import { managedRules } from "./managed";
import { pythonRules } from "./python";
import { systemsRules } from "./systems";
import type { BuiltInRule, RuleHit } from "./types";
import { universalRules } from "./universal";
import { workflowRules } from "./workflows";

export type { BuiltInRule, RuleHit, RuleLevel } from "./types";

export const builtInRules: readonly BuiltInRule[] = [
  ...universalRules,
  ...javascriptRules,
  ...pythonRules,
  ...systemsRules,
  ...managedRules,
  ...workflowRules,
];

export function checkBuiltInRules(files: readonly DiffFile[]): readonly RuleHit[] {
  return findRuleHits({ files, rules: builtInRules });
}
