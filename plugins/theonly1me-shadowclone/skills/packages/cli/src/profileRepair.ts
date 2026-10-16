import path from "node:path";
import { readLocalText, projectPaths, type ProjectPaths } from "@shadowclone/core";
import { readEnvironment } from "@shadowclone/environment";
import {
  applyProfileCuration,
  applyProfileRepair,
  createProfileCurationPlan,
  createProfileRepairPlan,
  parseProfileCurationDecisions,
  type ProfileCurationPlan,
  type ProfileRepairPlan,
} from "@shadowclone/profile";

type ProfileRepairOptions = {
  readonly apply: boolean;
  readonly decisionsPath: string | null;
};

function parseOptions(
  arguments_: readonly string[],
): ProfileRepairOptions | null {
  let apply = false;
  let decisionsPath: string | null = null;

  for (let index = 0; index < arguments_.length; index += 1) {
    const argument = arguments_[index];

    if (argument === "--apply" && !apply) {
      apply = true;
      continue;
    }

    if (argument === "--decisions" && decisionsPath === null) {
      const value = arguments_[index + 1];

      if (value === undefined) {
        return null;
      }

      decisionsPath = path.resolve(value);
      index += 1;
      continue;
    }

    return null;
  }

  return { apply, decisionsPath };
}

export function renderProfileRepairPlan(plan: ProfileRepairPlan): string {
  const lines = [
    `Profile repair: ${plan.repairs.length} ready, ${plan.blocked.length} blocked, ${plan.isolatedDirectories} isolated.`,
    ...plan.repairs.map(
      (repair) =>
        `  ${repair.sourceDirectory} -> ${repair.targetDirectory}: ${repair.files} file(s)`,
    ),
    ...plan.blocked.map(
      (repair) =>
        `  BLOCKED ${repair.sourceDirectory} -> ${repair.targetDirectory}: ${repair.reason}`,
    ),
  ];

  return `${lines.join("\n")}\n`;
}

export function renderProfileCurationPlan(plan: ProfileCurationPlan): string {
  return `Profile curation: ${plan.moves} move(s), ${plan.rejections} rejection(s), ${plan.references} reference conversion(s).\n`;
}

export async function handleProfileRepairCommand(options: {
  readonly command: string | undefined;
  readonly arguments: readonly string[];
  readonly paths?: ProjectPaths;
}): Promise<boolean> {
  if (options.command !== "profile" || options.arguments[0] !== "repair") {
    return false;
  }

  const flags = parseOptions(options.arguments.slice(1));

  if (flags === null) {
    throw new Error(
      "Use shadowclone profile repair [--decisions <file>] [--apply]",
    );
  }

  const paths = options.paths ?? projectPaths;

  if (await readEnvironment(paths)) {
    throw new Error(
      "The profile is archived after skills migration. Inspect active learning with skills pending or context --explain.",
    );
  }

  if (flags.decisionsPath !== null) {
    const text = await readLocalText(flags.decisionsPath);

    if (text === null) {
      throw new Error("Profile repair decisions file was not found");
    }

    const decisions = parseProfileCurationDecisions(text);
    const plan = await createProfileCurationPlan({ paths, decisions });

    await Bun.stdout.write(renderProfileCurationPlan(plan));

    if (!flags.apply) {
      await Bun.stdout.write(
        "Preview only. Run with --apply to create a revision-backed curation.\n",
      );

      return true;
    }

    const result = await applyProfileCuration({ paths, plan });

    await Bun.stdout.write(
      result.revisionId === null
        ? "No profile curation changes were needed.\n"
        : `Applied profile curation revision ${result.revisionId}.\n`,
    );

    return true;
  }

  const plan = await createProfileRepairPlan(paths);

  await Bun.stdout.write(renderProfileRepairPlan(plan));

  if (!flags.apply) {
    await Bun.stdout.write(
      "Preview only. Run with --apply to create a revision-backed repair.\n",
    );

    return true;
  }

  const result = await applyProfileRepair({ paths, plan });

  await Bun.stdout.write(
    result.revisionId === null
      ? "No profile repair changes were needed.\n"
      : `Applied profile repair revision ${result.revisionId}.\n`,
  );

  return true;
}
