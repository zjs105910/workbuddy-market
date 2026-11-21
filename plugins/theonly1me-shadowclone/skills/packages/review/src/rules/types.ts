import type { Finding } from "../types";

export type RuleLevel = "certain" | "signal";

export type BuiltInRule = {
  readonly id: string;
  readonly level: RuleLevel;
  readonly severity: Finding["severity"];
  readonly category: "security" | "correctness";
  readonly files: RegExp;
  readonly pattern: RegExp;
  readonly title: string;
  readonly failure: string;
  readonly examples: { readonly hit: string; readonly miss: string };
};

export type RuleHit = {
  readonly ruleId: string;
  readonly level: RuleLevel;
  readonly severity: Finding["severity"];
  readonly category: "security" | "correctness";
  readonly title: string;
  readonly failure: string;
  readonly path: string;
  readonly line: number;
  readonly reference?: string;
  readonly detail?: string;
};

export const javascriptFiles = /\.(?:[cm]?[jt]sx?|vue|svelte)$/;
export const javascriptTestFiles = /(?:\.(?:test|spec)\.[cm]?[jt]sx?$|(?:^|\/)__tests__\/)/;
export const pythonFiles = /\.pyi?$/;
export const goFiles = /\.go$/;
export const rustFiles = /\.rs$/;
export const jvmFiles = /\.(?:java|kt)$/;
export const csharpFiles = /\.cs$/;
export const cFamilyFiles = /\.(?:[cm]?[jt]sx?|java|kt|cs|cpp|cc|swift|php|dart|scala)$/;
export const workflowFiles = /^\.github\/(?:workflows\/[^/]+|actions\/.+\/action)\.ya?ml$/;
export const scriptFiles = /(?:\.(?:sh|bash|zsh|ya?ml)|(?:^|\/)(?:Dockerfile[^/]*|Makefile))$/;
export const configFiles = /\.(?:env[^/]*|ya?ml|json|toml|ini|conf|cfg|sh)$|(?:^|\/)\.env[^/]*$|(?:^|\/)Dockerfile[^/]*$/;
export const sqlFiles = /(?:\.sql$|(?:^|\/)migrations?\/)/i;
export const terraformFiles = /\.(?:tf|tf\.json)$/;
export const manifestFiles = /\.(?:ya?ml|json|tf)$/;
export const dockerFiles = /(?:^|\/)Dockerfile[^/]*$/;
