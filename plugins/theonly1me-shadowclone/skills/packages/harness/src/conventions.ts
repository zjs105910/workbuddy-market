import type { Convention } from "@shadowclone/environment";
import type { RepositoryFacts } from "./types";

const fileLengthPattern =
  /\b(?:under|at most|no more than|fewer than|below|maximum of|max(?:imum)?)\s+(\d{2,5})\s+lines\b/i;
const negativeDirective = /\b(?:never|no|don't|do not|avoid|without)\b/i;
const suppressionPattern =
  /\b(?:suppress(?:ion)?s?|eslint-disable|noqa)\b|@ts-(?:ignore|expect-error)|type:\s*ignore/i;
const commentPattern =
  /\b(?:zero|no|never (?:write|add))\s+(?:code\s+)?comments\b/i;
const emDashPattern = /\bem[- ]?dash(?:es)?\b/i;

function lineConventions(options: {
  readonly line: string;
  readonly facts: RepositoryFacts;
}): readonly Convention[] {
  const { line } = options;
  const conventions: Convention[] = [];
  const length = fileLengthPattern.exec(line)?.[1];

  if (length !== undefined) {
    conventions.push({ kind: "file-length", maximumLines: Number(length) });
  }

  if (emDashPattern.test(line) && negativeDirective.test(line)) {
    conventions.push({
      kind: "forbidden-text",
      name: "em-dash",
      text: "\u2014",
    });
  }

  if (suppressionPattern.test(line) && negativeDirective.test(line)) {
    conventions.push({ kind: "no-suppressions" });
  }

  if (commentPattern.test(line) && options.facts.tools.has("typescript")) {
    conventions.push({ kind: "no-comments", language: "typescript" });
  }

  return conventions;
}

export function deriveConventions(options: {
  readonly ruleLines: string;
  readonly facts: RepositoryFacts;
}): readonly Convention[] {
  const derived = options.ruleLines
    .split("\n")
    .flatMap((line) => lineConventions({ line, facts: options.facts }));
  const unique = new Map<string, Convention>();

  for (const convention of derived) {
    const key =
      convention.kind === "forbidden-text"
        ? `${convention.kind}:${convention.name}`
        : convention.kind;
    const existing = unique.get(key);

    if (existing?.kind === "file-length" && convention.kind === "file-length") {
      unique.set(key, {
        kind: "file-length",
        maximumLines: Math.min(existing.maximumLines, convention.maximumLines),
      });
    } else if (existing === undefined) {
      unique.set(key, convention);
    }
  }

  return [...unique.values()];
}

export function sourceExtensions(facts: RepositoryFacts): readonly string[] {
  const extensions = new Set<string>();

  if (facts.node !== null) {
    for (const extension of [".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"]) {
      extensions.add(extension);
    }
  }

  if (facts.python !== null) {
    extensions.add(".py");
  }

  if (facts.rust) {
    extensions.add(".rs");
  }

  if (facts.go) {
    extensions.add(".go");
  }

  return [...extensions];
}
