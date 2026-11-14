import { existsSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { readLocalText, replaceLocalText } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import { resolveRedacted } from "@shadowclone/sessions";
import { proposalSchema, type SkillProposal } from "./types";

export function proposalPath(options: {
  readonly paths: ProjectPaths;
  readonly id: string;
}): string {
  if (!z.uuid().safeParse(options.id).success) {
    throw new Error("Proposal id must be a UUID");
  }

  return path.join(
    options.paths.shadowcloneDirectory,
    "skill-proposals",
    `${options.id}.json`,
  );
}

export async function readSkillProposal(options: {
  readonly paths: ProjectPaths;
  readonly id: string;
}): Promise<SkillProposal> {
  const contents = await readLocalText(proposalPath(options));

  try {
    return proposalSchema.parse(JSON.parse(contents ?? "null"));
  } catch {
    throw new Error("Skill proposal was not found or is invalid");
  }
}

export async function saveSkillProposal(options: {
  readonly paths: ProjectPaths;
  readonly proposal: SkillProposal;
}): Promise<void> {
  const filePath = proposalPath({
    paths: options.paths,
    id: options.proposal.id,
  });

  await replaceLocalText({
    filePath,
    previous: await readLocalText(filePath),
    next: `${JSON.stringify(proposalSchema.parse(options.proposal), null, 2)}\n`,
  });
}

export async function listSkillProposals(paths: ProjectPaths): Promise<
  readonly {
    readonly id: string;
    readonly status: SkillProposal["status"];
    readonly kind: SkillProposal["kind"];
    readonly findings: readonly string[];
    readonly createdAt: number;
  }[]
> {
  const directory = path.join(paths.shadowcloneDirectory, "skill-proposals");

  if (!existsSync(directory)) {
    return [];
  }

  const proposals = [];

  for await (const filename of new Bun.Glob("*.json").scan({
    cwd: directory,
    onlyFiles: true,
  })) {
    const proposal = await readSkillProposal({
      paths,
      id: filename.slice(0, -5),
    });

    proposals.push({
      id: proposal.id,
      status: proposal.status,
      kind: proposal.kind,
      findings: proposal.findings,
      createdAt: proposal.createdAt,
    });
  }

  return proposals.sort((left, right) => right.createdAt - left.createdAt);
}

export async function showSkillProposal(options: {
  readonly paths: ProjectPaths;
  readonly id: string;
}): Promise<string> {
  await readSkillProposal(options);

  const sourcePath = proposalPath(options);

  return resolveRedacted({
    roots: [options.paths.shadowcloneDirectory],
    ref: {
      type: "file",
      sourcePath,
      byteOffset: 0,
      byteLength: Bun.file(sourcePath).size,
    },
  });
}
