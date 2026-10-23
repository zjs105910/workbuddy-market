import { lstat } from "node:fs/promises";
import path from "node:path";
import { type HarnessManifest, harnessMarkers, markedSection } from "@shadowclone/environment";
import { fingerprint, readLocalText } from "@shadowclone/core";
import { parseSkillDocument } from "@shadowclone/skills";
import { repositorySkillRoots } from "../plan/skills";
import type { HarnessFinding } from "./types";
import { error, warning, refresh } from "./healthFinding";
import { gateFindings } from "./gateHealth";

const maximumAgentsLines = 150;
async function agentsFindings(options: {
  readonly root: string;
  readonly manifest: HarnessManifest;
}): Promise<readonly HarnessFinding[]> {
  const text = await readLocalText(path.join(options.root, "AGENTS.md"));

  if (text === null) {
    return [
      error({
        rule: "agents-missing",
        path: "AGENTS.md",
        fix: `AGENTS.md is missing; ${refresh} to restore it.`,
      }),
    ];
  }

  const section = markedSection({ text, markers: harnessMarkers });
  const findings: HarnessFinding[] = [];

  if (section === null) {
    findings.push(
      error({
        rule: "agents-section",
        path: "AGENTS.md",
        fix: `AGENTS.md lost its Shadowclone section; ${refresh}.`,
      }),
    );
  } else if (fingerprint(section) !== options.manifest.artifacts["AGENTS.md"]) {
    findings.push(
      warning({
        rule: "agents-edited",
        path: "AGENTS.md",
        fix: `The Shadowclone section in AGENTS.md was edited. Move team notes outside the markers, then ${refresh}.`,
      }),
    );
  }

  const lines = text.split("\n").length;

  if (lines > maximumAgentsLines) {
    findings.push(
      warning({
        rule: "agents-length",
        path: "AGENTS.md",
        fix: `AGENTS.md has ${lines} lines. Keep it at or under ${maximumAgentsLines} by linking to longer documents.`,
      }),
    );
  }

  return findings;
}

async function claudeFindings(
  root: string,
): Promise<readonly HarnessFinding[]> {
  const filePath = path.join(root, "CLAUDE.md");

  if ((await lstat(filePath).catch(() => null))?.isSymbolicLink()) {
    return [];
  }

  const text = await readLocalText(filePath);
  const imports =
    text?.split("\n").some((line) => line.trim() === "@AGENTS.md") ?? false;

  return imports
    ? []
    : [
        warning({
          rule: "claude-import",
          path: "CLAUDE.md",
          fix: `CLAUDE.md does not import AGENTS.md, so Claude may not read it; ${refresh}.`,
        }),
      ];
}

async function skillFindings(options: {
  readonly root: string;
  readonly manifest: HarnessManifest;
}): Promise<readonly HarnessFinding[]> {
  const findings: HarnessFinding[] = [];

  for (const name of options.manifest.skills) {
    for (const skillRoot of repositorySkillRoots) {
      const relativePath = `${skillRoot}/${name}/SKILL.md`;
      const text = await readLocalText(path.join(options.root, relativePath));
      let valid = false;

      try {
        valid =
          text !== null && parseSkillDocument(text).metadata.name === name;
      } catch {
        valid = false;
      }

      if (!valid) {
        findings.push(
          error({
            rule: "skill-invalid",
            path: relativePath,
            fix: `Skill ${name} is missing or its frontmatter is invalid; ${refresh} or fix its name and description.`,
          }),
        );
      }
    }
  }

  return findings;
}

export async function healthFindings(options: {
  readonly root: string;
  readonly manifest: HarnessManifest;
}): Promise<readonly HarnessFinding[]> {
  return [
    ...(await agentsFindings(options)),
    ...(await claudeFindings(options.root)),
    ...(await skillFindings(options)),
    ...(await gateFindings(options)),
  ];
}
