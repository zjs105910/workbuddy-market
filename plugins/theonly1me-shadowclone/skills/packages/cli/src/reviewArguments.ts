import { reasoningEfforts, type ReasoningEffort } from "@shadowclone/agents";

export type ReviewTarget =
  | { readonly kind: "pull"; readonly number: number }
  | { readonly kind: "branch"; readonly base: string | null };

export type LocalReviewArguments = {
  readonly target: ReviewTarget;
  readonly repository: string | null;
  readonly runChecks: boolean;
  readonly network: boolean;
  readonly cloud: boolean;
  readonly output: string | null;
  readonly model: string;
  readonly effort: ReasoningEffort | null;
};

export const defaultReviewModel = "claude-opus-5-5";

export const reviewUsage =
  "Use shadowclone review <pr-number> [--cloud] for a pull request, or shadowclone review [--base ref] for the current branch. Options: [--no-checks] [--offline] [--repo owner/repository] [--output file.md] [--model id] [--effort level].";

const valueFlags = ["--repo", "--output", "--model", "--effort", "--base"] as const;
const switchFlags = ["--cloud", "--no-checks", "--offline"] as const;

function isReasoningEffort(value: string): value is ReasoningEffort {
  return reasoningEfforts.some((effort) => effort === value);
}

function reviewTarget(options: { readonly positionals: readonly string[]; readonly base: string | null }): ReviewTarget {
  const [numberText, ...extra] = options.positionals;

  if (numberText === undefined) {
    return { kind: "branch", base: options.base };
  }

  const number = Number(numberText);

  if (extra.length > 0 || options.base !== null || !Number.isInteger(number) || number <= 0) {
    throw new Error(reviewUsage);
  }

  return { kind: "pull", number };
}

export function parseReviewArguments(arguments_: readonly string[]): LocalReviewArguments {
  const values = new Map<string, string>();
  const switches = new Set<string>();
  const positionals: string[] = [];

  for (let position = 0; position < arguments_.length; position += 1) {
    const argument = arguments_[position] ?? "";

    if (switchFlags.some((flag) => flag === argument)) {
      switches.add(argument);
      continue;
    }

    if (valueFlags.some((flag) => flag === argument)) {
      const value = arguments_[position + 1];

      if (value === undefined || value.startsWith("-") || values.has(argument)) {
        throw new Error(reviewUsage);
      }

      values.set(argument, value);
      position += 1;
      continue;
    }

    if (argument.startsWith("-")) {
      throw new Error(reviewUsage);
    }

    positionals.push(argument);
  }

  const repository = values.get("--repo") ?? null;
  const effort = values.get("--effort") ?? null;
  const target = reviewTarget({ positionals, base: values.get("--base") ?? null });

  if (target.kind === "branch" && switches.has("--cloud")) {
    throw new Error("A cloud review needs a pull request number, for example shadowclone review 123 --cloud.");
  }

  if (repository !== null && !/^[\w.-]+\/[\w.-]+$/.test(repository)) {
    throw new Error(reviewUsage);
  }

  if (effort !== null && !isReasoningEffort(effort)) {
    throw new Error(`Choose an effort from ${reasoningEfforts.join(", ")}.`);
  }

  return {
    target,
    repository,
    runChecks: !switches.has("--no-checks"),
    network: !switches.has("--offline"),
    cloud: switches.has("--cloud"),
    output: values.get("--output") ?? null,
    model: values.get("--model") ?? defaultReviewModel,
    effort,
  };
}
