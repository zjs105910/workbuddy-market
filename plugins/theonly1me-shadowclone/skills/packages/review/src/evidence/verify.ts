import { readFile } from "node:fs/promises";
import path from "node:path";
import type { DiffFile } from "../collect";
import type { RuleHit } from "../rules";
import type { CommandReport } from "../toolchain";
import type { Evidence, Finding } from "../types";
import { diffContent, normalizeCode, normalizeProse, parseCodeLocation } from "./match";

export type EvidenceSources = {
  readonly checkout: string;
  readonly files: readonly DiffFile[];
  readonly ruleHits: readonly RuleHit[];
  readonly toolchain: readonly CommandReport[];
  readonly fetchText: (url: string) => Promise<string | null>;
};

export type EvidenceCheck = { readonly verified: true } | { readonly verified: false; readonly reason: string };

const contextLines = 3;

export async function readHeadLines(options: { readonly checkout: string; readonly relativePath: string }): Promise<readonly string[] | null> {
  const resolved = path.resolve(options.checkout, options.relativePath);
  const relative = path.relative(options.checkout, resolved);

  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    return null;
  }

  const text = await readFile(resolved, "utf8").catch(() => null);

  return text === null ? null : text.split("\n");
}

async function checkCode(options: { readonly item: Evidence; readonly sources: EvidenceSources }): Promise<EvidenceCheck> {
  const location = parseCodeLocation(options.item.location);
  const lines = location ? await readHeadLines({ checkout: options.sources.checkout, relativePath: location.path }) : null;

  if (location === null || lines === null) {
    return { verified: false, reason: `\`${options.item.location}\` is not a file and line at the head` };
  }

  const window = lines.slice(Math.max(0, location.start - 1 - contextLines), location.end + contextLines).join("\n");

  return normalizeCode(window).includes(normalizeCode(options.item.quote))
    ? { verified: true }
    : { verified: false, reason: `the quoted code is not at \`${options.item.location}\`` };
}

function checkDiff(options: { readonly item: Evidence; readonly sources: EvidenceSources }): EvidenceCheck {
  const filePath = parseCodeLocation(options.item.location)?.path ?? options.item.location.trim();
  const file = options.sources.files.find((entry) => entry.path === filePath);

  return file !== undefined && normalizeCode(diffContent(file.text)).includes(normalizeCode(options.item.quote))
    ? { verified: true }
    : { verified: false, reason: `the quoted change is not in the diff of \`${filePath}\`` };
}

function checkRule(options: { readonly item: Evidence; readonly sources: EvidenceSources }): EvidenceCheck {
  const location = parseCodeLocation(options.item.location);
  const found = options.sources.ruleHits.some(
    (hit) => hit.ruleId === options.item.quote.trim() && hit.path === location?.path && hit.line === location.start,
  );

  return found ? { verified: true } : { verified: false, reason: `no rule hit \`${options.item.quote}\` at \`${options.item.location}\`` };
}

function checkToolchain(options: { readonly item: Evidence; readonly sources: EvidenceSources }): EvidenceCheck {
  const location = parseCodeLocation(options.item.location);
  const quote = normalizeProse(options.item.quote);
  const found = options.sources.toolchain.some((report) =>
    report.diagnostics.some(
      (diagnostic) =>
        diagnostic.path === location?.path && diagnostic.line === location.start && normalizeProse(diagnostic.message).includes(quote),
    ),
  );

  return found ? { verified: true } : { verified: false, reason: `no toolchain diagnostic matches at \`${options.item.location}\`` };
}

async function checkDoc(options: { readonly item: Evidence; readonly sources: EvidenceSources }): Promise<EvidenceCheck> {
  const text = await options.sources.fetchText(options.item.location.trim());

  return text !== null && normalizeProse(text).includes(normalizeProse(options.item.quote))
    ? { verified: true }
    : { verified: false, reason: `the quote is not on ${options.item.location}` };
}

export async function checkEvidence(options: { readonly item: Evidence; readonly sources: EvidenceSources }): Promise<EvidenceCheck> {
  const checks = {
    code: checkCode,
    diff: async (input: typeof options) => checkDiff(input),
    rule: async (input: typeof options) => checkRule(input),
    toolchain: async (input: typeof options) => checkToolchain(input),
    doc: checkDoc,
  } as const;

  return checks[options.item.source](options);
}

export function findingLocationExists(options: { readonly finding: Finding; readonly lines: readonly string[] | null }): boolean {
  return options.lines !== null && options.finding.line <= options.lines.length;
}
