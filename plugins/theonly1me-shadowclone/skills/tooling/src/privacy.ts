import { stat } from "node:fs/promises";
import path from "node:path";
import privacyTerms from "./privacyTerms.json";

export type PrivacyFinding = {
  readonly file: string;
  readonly line: number;
  readonly rule: "email" | "home-path" | "issue-reference" | "url" | "pronoun" | "private-term";
  readonly message: string;
};

export type PrivacyReport = {
  readonly checkedFileCount: number;
  readonly findings: readonly PrivacyFinding[];
};

const scannedDirectories = ["skills", "preferences", "plugins/shadowclone/skills"] as const;
const textExtensions = [
  ".md",
  ".mjs",
  ".js",
  ".ts",
  ".json",
  ".html",
  ".css",
  ".txt",
  ".sh",
  ".yml",
  ".yaml",
];
const allowedUrlPrefixes = [
  "code.claude.com/",
  "docs.claude.com/",
  "platform.claude.com/",
  "learn.chatgpt.com/",
  "developers.openai.com/",
  "agentskills.io/",
  "asd-ste100.org/",
  "www.asd-ste100.org/",
  "cdn.jsdelivr.net/npm/",
  "www.w3.org/",
  "json-schema.org/",
  "example.com/",
  "github.com/theonly1me/shadowclone",
];
const allowedEmailDomains = ["example.com", "example.org", "example.net"];
const emailPattern = /\b([A-Za-z0-9._%+-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b/g;
const homePathPattern = /(?:^|[\s`'"(])(\/(?:Users|home)\/[^\s`'")/]+)/g;
const issueReferencePattern = /\b[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+#\d+\b/g;
const urlPattern = /https?:\/\/([^\s)"'`<>]+)/g;
const pronounPattern = /\b(?:he|him|his|himself|she|her|hers|herself)\b/i;

export function normalizeTerm(term: string): string {
  return (term.toLowerCase().match(/[a-z0-9]+/g) ?? []).join(" ");
}

export function hashTerm(term: string): string {
  return new Bun.CryptoHasher("sha256").update(normalizeTerm(term)).digest("hex");
}

function phraseHashes(line: string): ReadonlyMap<string, string> {
  const words = normalizeTerm(line).split(" ").filter(Boolean);
  const hashes = new Map<string, string>();

  for (let start = 0; start < words.length; start += 1) {
    for (let length = 1; length <= 3 && start + length <= words.length; length += 1) {
      const phrase = words.slice(start, start + length).join(" ");

      hashes.set(hashTerm(phrase), phrase);
    }
  }

  return hashes;
}

function lineFindings(options: {
  readonly file: string;
  readonly line: number;
  readonly text: string;
  readonly privateHashes: ReadonlySet<string>;
}): readonly PrivacyFinding[] {
  const at = { file: options.file, line: options.line };
  const findings: PrivacyFinding[] = [];

  for (const [address, , domain = ""] of options.text.matchAll(emailPattern)) {
    if (address !== "git@github.com" && !allowedEmailDomains.includes(domain.toLowerCase())) {
      findings.push({
        ...at,
        rule: "email",
        message: `${address} is a real address, use an example.com address`,
      });
    }
  }

  for (const [, homePath = ""] of options.text.matchAll(homePathPattern)) {
    findings.push({
      ...at,
      rule: "home-path",
      message: `${homePath} names a machine, write the path with ~`,
    });
  }

  for (const [reference] of options.text.matchAll(issueReferencePattern)) {
    findings.push({
      ...at,
      rule: "issue-reference",
      message: `${reference} names a real repository item`,
    });
  }

  for (const [url, target = ""] of options.text.matchAll(urlPattern)) {
    if (!allowedUrlPrefixes.some((prefix) => target.startsWith(prefix))) {
      findings.push({
        ...at,
        rule: "url",
        message: `${url} is not on the allowlist in tooling/src/privacy.ts`,
      });
    }
  }

  if (options.file.endsWith(".md") && pronounPattern.test(options.text)) {
    findings.push({
      ...at,
      rule: "pronoun",
      message: 'write "the user" instead of a gendered pronoun',
    });
  }

  for (const [hash, phrase] of phraseHashes(options.text)) {
    if (options.privateHashes.has(hash)) {
      findings.push({ ...at, rule: "private-term", message: `"${phrase}" matches a private term` });
    }
  }

  return findings;
}

async function directoryExists(directory: string): Promise<boolean> {
  try {
    return (await stat(directory)).isDirectory();
  } catch {
    return false;
  }
}

async function listShippedFiles(rootDirectory: string): Promise<readonly string[]> {
  const files: string[] = [];

  for (const directory of scannedDirectories) {
    const absolute = path.join(rootDirectory, directory);

    if (!(await directoryExists(absolute))) {
      continue;
    }

    for await (const file of new Bun.Glob("**/*").scan({ cwd: absolute, onlyFiles: true })) {
      if (textExtensions.some((extension) => file.endsWith(extension))) {
        files.push(path.join(directory, file));
      }
    }
  }

  return files.sort();
}

export async function findPrivacyFindings(options: {
  readonly rootDirectory: string;
  readonly privateTerms?: readonly string[];
}): Promise<PrivacyReport> {
  const privateHashes = new Set([
    ...privacyTerms.sha256,
    ...(options.privateTerms ?? []).map(hashTerm),
  ]);
  const files = await listShippedFiles(options.rootDirectory);
  const findings: PrivacyFinding[] = [];

  for (const file of files) {
    const text = await Bun.file(path.join(options.rootDirectory, file)).text();

    for (const [index, line] of text.split("\n").entries()) {
      findings.push(...lineFindings({ file, line: index + 1, text: line, privateHashes }));
    }
  }

  return { checkedFileCount: files.length, findings };
}

if (import.meta.main) {
  const argumentsAfterScript = Bun.argv.slice(2);
  const [flag, value] = argumentsAfterScript;

  if (flag === "--hash" && value !== undefined) {
    console.log(`"${normalizeTerm(value)}" ${hashTerm(value)}`);
  } else {
    const termsFile = flag === "--terms" && value !== undefined ? value : null;
    const privateTerms = termsFile
      ? (await Bun.file(termsFile).text()).split("\n").filter((term) => term.trim().length > 0)
      : [];
    const report = await findPrivacyFindings({ rootDirectory: process.cwd(), privateTerms });

    for (const finding of report.findings) {
      console.log(`${finding.file}:${finding.line} ${finding.rule} ${finding.message}`);
    }

    console.log(
      `privacy: checked ${report.checkedFileCount} files, found ${report.findings.length} findings`,
    );

    if (report.findings.length > 0) {
      process.exitCode = 1;
    }
  }
}
