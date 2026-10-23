#!/usr/bin/env node
import { readFile } from "node:fs/promises";

const maximumWords = 25;
const dash = /[\u2013\u2014]/;
const passive =
  /\b(?:is|are|was|were|be|been|being)\s+(?:not\s+)?(?:\w+ly\s+)?(\w{3,}(?:ed|en))\b/i;
const notParticiples = new Set(["often", "even", "seven", "eleven", "token", "listen", "golden"]);
const phrasalVerbs = [
  "carry out",
  "come up with",
  "end up",
  "figure out",
  "find out",
  "get rid of",
  "go over",
  "kick off",
  "look into",
  "make use of",
  "point out",
  "set up",
  "take care of",
  "turn out",
];
const vagueWords = [
  "basically",
  "etc",
  "leverage",
  "numerous",
  "robust",
  "seamless",
  "seamlessly",
  "simply",
  "utilize",
  "various",
];

function proseLines(text) {
  const lines = text.split("\n");
  const prose = [];
  let fence = null;
  let frontmatter = lines[0] === "---";

  for (const [index, line] of lines.entries()) {
    const number = index + 1;

    if (frontmatter) {
      if (index > 0 && line === "---") {
        frontmatter = false;
      }

      const description = /^description:\s*(["']?)(.*)\1\s*$/.exec(line);

      if (description) {
        prose.push({ number, text: description[2].replace(/''/g, "'") });
      }

      continue;
    }

    const marker = /^\s*(`{3,}|~{3,})/.exec(line)?.[1];

    if (marker) {
      fence = fence === null ? marker : marker.startsWith(fence) ? null : fence;

      continue;
    }

    if (fence !== null || /^\s*(?:#|\||$)/.test(line)) {
      continue;
    }

    prose.push({
      number,
      text: line
        .replace(/`[^`]*`/g, "Code")
        .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
        .replace(/^\s*(?:[-*]|\d+\.)\s+/, "")
        .replace(/\*\*([^*]+):\*\*/g, "$1:")
        .replace(/[*_]/g, ""),
    });
  }

  return prose;
}

function sentencesOf(text) {
  return text
    .split(/(?<=[.!?])\s+(?=["'(A-Z0-9])/)
    .map((sentence) => sentence.trim())
    .filter((sentence) => sentence.length > 0);
}

function wordCount(sentence) {
  return sentence.split(/\s+/).filter((word) => /[A-Za-z0-9]/.test(word)).length;
}

function checkText(text) {
  const findings = [];

  for (const line of proseLines(text)) {
    if (dash.test(line.text)) {
      findings.push({
        line: line.number,
        level: "error",
        rule: "dash",
        message: "replace the em or en dash with a comma, a period, parentheses, or the word to",
      });
    }

    for (const sentence of sentencesOf(line.text)) {
      const words = wordCount(sentence);
      const unquoted = sentence.replace(/"[^"]*"/g, " ");
      const lower = ` ${unquoted.toLowerCase().replace(/[^a-z0-9' ]+/g, " ")} `;
      const passiveMatch = passive.exec(unquoted);
      const passiveWord = passiveMatch?.[1]?.toLowerCase();

      if (words > maximumWords) {
        findings.push({
          line: line.number,
          level: "error",
          rule: "long-sentence",
          message: `${words} words, split it to ${maximumWords} or fewer: "${sentence.slice(0, 60)}"`,
        });
      }

      if (passiveMatch && passiveWord && !notParticiples.has(passiveWord)) {
        findings.push({
          line: line.number,
          level: "warning",
          rule: "passive",
          message: `"${passiveMatch[0]}" may be passive, name who does the action`,
        });
      }

      for (const verb of phrasalVerbs.filter((entry) => lower.includes(` ${entry} `))) {
        findings.push({
          line: line.number,
          level: "warning",
          rule: "phrasal-verb",
          message: `"${verb}" is a phrasal verb, use a single verb`,
        });
      }

      for (const word of vagueWords.filter((entry) => lower.includes(` ${entry} `))) {
        findings.push({
          line: line.number,
          level: "warning",
          rule: "vague-word",
          message: `"${word}" is vague, say exactly what you mean`,
        });
      }
    }
  }

  return findings;
}

async function main(files) {
  if (files.length === 0) {
    console.error("Usage: check-ste.mjs <file>...");

    return 2;
  }

  let errors = 0;
  let warnings = 0;

  for (const file of files) {
    let text;

    try {
      text = await readFile(file, "utf8");
    } catch (error) {
      console.error(`${file}: cannot read the file (${error.code ?? error.message})`);

      return 2;
    }

    for (const finding of checkText(text)) {
      console.log(`${file}:${finding.line}: ${finding.level} ${finding.rule} ${finding.message}`);

      if (finding.level === "error") {
        errors += 1;
      } else {
        warnings += 1;
      }
    }
  }

  const plural = (count, word) => `${count} ${word}${count === 1 ? "" : "s"}`;

  console.log(
    `check-ste: ${plural(errors, "error")}, ${plural(warnings, "warning")} in ${plural(files.length, "file")}`,
  );

  return errors > 0 ? 1 : 0;
}

process.exitCode = await main(process.argv.slice(2));
