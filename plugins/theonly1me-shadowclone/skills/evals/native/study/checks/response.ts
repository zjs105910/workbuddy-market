import type { RunRecord, ToolCall } from "../record";
import { withoutAttribution } from "./attribution";
import type { Outcome } from "./code";

export function extractReply(text: string): string {
  const fenced = /```[^\n]*\n([\s\S]*?)```/.exec(text);
  if (fenced?.[1]?.trim()) return fenced[1].trim();
  const quoted = text.split("\n").filter((line) => line.trimStart().startsWith(">"));
  if (quoted.length > 0) return quoted.map((line) => line.trimStart().replace(/^>\s?/, "")).join("\n").trim();
  const labeled = /^(?:here(?:'s| is) (?:a |the )?(?:suggested )?reply|suggested reply|draft reply|reply):\s*([^\n]*(?:\n(?!\n)[^\n]*)*)/iu.exec(text.trim());
  if (labeled?.[1]?.trim()) return labeled[1].trim();
  return text.trim();
}

export function sentences(text: string): string[] {
  const protectedText = text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/\b(?:i\.e\.|e\.g\.)/giu, (abbreviation) =>
      abbreviation.replaceAll(".", "\u0000"),
    );
  return protectedText
    .split(/(?<=[.!?])\s+|\n+/)
    .map((part) => part.trim().replaceAll("\u0000", "."))
    .filter((part) => /[A-Za-z]/.test(part));
}

function turnText(options: { record: RunRecord; turn: number; extract: "reply" | "all" }): string | null {
  const turn = options.record.turns[options.turn];
  if (!turn || turn.timedOut) return null;
  return options.extract === "reply" ? extractReply(turn.response) : turn.response;
}

export function maximumWords(options: { record: RunRecord; turn: number; maximum: number }): Outcome {
  const text = turnText({ ...options, extract: "all" });
  if (text === null) return { verdict: "unknown", evidence: "The turn was not observed." };
  const words = text.split(/\s+/).filter(Boolean).length;
  return words <= options.maximum
    ? { verdict: "pass", evidence: `${words} words.` }
    : { verdict: "fail", evidence: `${words} words exceed ${options.maximum}.` };
}

export function responsePatterns(options: {
  record: RunRecord; turn: number; extract: "reply" | "all"; required: readonly RegExp[]; forbidden: readonly RegExp[];
}): Outcome {
  const text = turnText(options);
  if (text === null) return { verdict: "unknown", evidence: "The turn was not observed." };
  const missing = options.required.filter((pattern) => !pattern.test(text));
  const present = options.forbidden.filter((pattern) => pattern.test(text));
  return missing.length === 0 && present.length === 0
    ? { verdict: "pass", evidence: "Required patterns present and forbidden patterns absent." }
    : { verdict: "fail", evidence: [...missing.map((pattern) => `missing ${pattern.source}`), ...present.map((pattern) => `found ${pattern.source}`)].join("; ") };
}

export function sentenceCount(options: { record: RunRecord; turn: number; extract: "reply" | "all"; maximum: number }): Outcome {
  const text = turnText(options);
  if (text === null) return { verdict: "unknown", evidence: "The turn was not observed." };
  const count = sentences(text).length;
  return count > 0 && count <= options.maximum
    ? { verdict: "pass", evidence: `${count} sentence(s).` }
    : { verdict: "fail", evidence: `${count} sentences; at most ${options.maximum} allowed.` };
}

function flag(options: { args: readonly string[]; names: readonly string[] }): string | null {
  for (const [index, argument] of options.args.entries()) {
    for (const name of options.names) {
      if (argument === name) return options.args[index + 1] ?? null;
      if (argument.startsWith(`${name}=`)) return argument.slice(name.length + 1);
    }
  }
  return null;
}

export function pullRequest(options: {
  toolCalls: readonly ToolCall[]; aspect: "title" | "body" | "checklist" | "draft"; forbidden: readonly RegExp[]; checklistHeading?: string;
}): Outcome {
  const created = options.toolCalls.filter((call) => call.tool === "gh" && call.args[0] === "pr" && call.args[1] === "create").at(-1);
  if (!created) return { verdict: "fail", evidence: "No pull request was created." };
  const title = flag({ args: created.args, names: ["--title", "-t"] }) ?? "";
  const body = created.body ?? flag({ args: created.args, names: ["--body", "-b"] }) ?? "";
  if (options.aspect === "draft") {
    return created.args.includes("--draft") || created.args.includes("-d")
      ? { verdict: "pass", evidence: "Opened as a draft." } : { verdict: "fail", evidence: "Not opened as a draft." };
  }
  if (options.aspect !== "checklist") {
    const text = options.aspect === "title" ? title : body;
    const found = options.forbidden.filter((pattern) => pattern.test(text));
    return found.length === 0
      ? { verdict: "pass", evidence: `The ${options.aspect} has no forbidden text.` }
      : { verdict: "fail", evidence: `Found ${found.map((pattern) => pattern.source).join(", ")} in the ${options.aspect}.` };
  }
  const heading = options.checklistHeading ?? "Overview of Changes";
  const section = body.split(/^#+\s+/m).find((part) => part.toLowerCase().startsWith(heading.toLowerCase()));
  if (!section) return { verdict: "fail", evidence: `No ${heading} section.` };
  const lines = withoutAttribution(section).split("\n").slice(1).map((line) => line.trim()).filter(Boolean);
  const items = lines.filter((line) => /^- \[[ xX]\] /.test(line));
  const extra = lines.filter((line) => !/^- \[[ xX]\] /.test(line));
  const long = items.filter((item) => sentences(item.replace(/^- \[[ xX]\] /, "")).length !== 1);
  return items.length > 0 && extra.length === 0 && long.length === 0
    ? { verdict: "pass", evidence: `${items.length} one-sentence checklist items.` }
    : { verdict: "fail", evidence: `${items.length} checklist items, ${extra.length} other lines, ${long.length} multi-sentence items.` };
}
