import { redactSecrets } from "@shadowclone/redact";
import { parseCodeLocation } from "../evidence/match";
import type { Evidence, Finding } from "../types";
import { neutralizeText } from "./neutralize";

export type LinkTarget = {
  readonly repository: string;
  readonly headSha: string;
};

const githubThread = /^https?:\/\/github\.com\/[\w.-]+\/[\w.-]+\/(?:issues|pull|discussions)\//;

export function inlineCode(text: string): string {
  const longestRun = Math.max(0, ...[...text.matchAll(/`+/g)].map((match) => match[0].length));
  const fence = "`".repeat(longestRun + 1);
  const padded = text.startsWith("`") || text.endsWith("`") ? ` ${text} ` : text;

  const joined = padded.replace(/\s+/g, (whitespace) => (whitespace.includes("\n") ? " " : whitespace));

  return `${fence}${joined}${fence}`;
}

function codeLink(options: { readonly location: string; readonly target: LinkTarget | null }): string {
  const parsed = parseCodeLocation(options.location);

  if (parsed === null || options.target === null) {
    return inlineCode(options.location);
  }

  const lines = parsed.end > parsed.start ? `L${parsed.start}-L${parsed.end}` : `L${parsed.start}`;
  const url = `https://github.com/${options.target.repository}/blob/${options.target.headSha}/${encodeURI(parsed.path)}#${lines}`;

  return `[\`${options.location}\`](${url})`;
}

function docLink(location: string): string {
  if (githubThread.test(location)) {
    return inlineCode(location);
  }

  try {
    return `[${new URL(location).hostname}](${location})`;
  } catch {
    return inlineCode(location);
  }
}

export function evidenceLine(options: { readonly item: Evidence; readonly target: LinkTarget | null }): string {
  const { target } = options;
  const item = { ...options.item, quote: redactSecrets({ text: options.item.quote }) };

  if (item.source === "code") {
    return `- ${codeLink({ location: item.location, target })}: ${inlineCode(item.quote)}`;
  }

  if (item.source === "diff") {
    return `- Diff of ${inlineCode(item.location)}: ${inlineCode(item.quote)}`;
  }

  if (item.source === "rule") {
    return `- Built-in rule ${inlineCode(item.quote)} at ${codeLink({ location: item.location, target })}`;
  }

  if (item.source === "toolchain") {
    return `- Toolchain at ${codeLink({ location: item.location, target })}: ${inlineCode(item.quote)}`;
  }

  return `- ${docLink(item.location)}: "${neutralizeText(item.quote)}"`;
}

export function findingBody(options: { readonly finding: Finding; readonly target: LinkTarget | null; readonly refutation: boolean }): string {
  const { finding, target } = options;
  const sections = [
    `**${finding.severity} ${finding.category}: ${neutralizeText(finding.title)}**`,
    neutralizeText(finding.explanation),
    `**Failure:** ${neutralizeText(finding.failureScenario)}`,
    ...(finding.rule ? [`**Rule:** ${neutralizeText(finding.rule)}`] : []),
    ["**Evidence:**", ...finding.evidence.map((item) => evidenceLine({ item, target }))].join("\n"),
    ...(finding.suggestion ? [`**Fix:** ${neutralizeText(finding.suggestion)}`] : []),
    ...(options.refutation ? [`**Refuter:** ${neutralizeText(finding.refutation)}`] : []),
  ];

  return sections.join("\n\n");
}
