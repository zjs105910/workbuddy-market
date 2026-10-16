import path from "node:path";
import type { FileUpdate } from "@shadowclone/changes";
import {
  type BuildContext,
  buildInputSchema,
  environmentFile,
  renderEnvironment,
} from "@shadowclone/environment";
import { fingerprint, readLocalText } from "@shadowclone/core";
import { authoredBuildSkills } from "./authored";
import { buildCatalog } from "./catalog";
import { planBuildRouting } from "./native";
import { prepareBuildEnvironment } from "./prepare";
import { publishBuildSkill, retireBuildSkills } from "./publication";
import { recordBuildPreferences } from "./records";
import { buildDefinition, selectedItems } from "./selection";
import type { BuildPlan } from "./types";

export async function previewBuild(
  options: BuildContext & { readonly input: unknown },
): Promise<BuildPlan> {
  const input = buildInputSchema.parse(options.input);

  for (const skill of input.custom) {
    input.choices[`custom:${skill.name}`] ??= true;
  }

  let state = await prepareBuildEnvironment(options);
  const catalog = await buildCatalog({ ...options, scope: input.scope });

  for (const item of catalog) {
    if (item.alwaysOn) {
      input.choices[item.id] = true;
    }
  }

  const build = buildDefinition({ ...options, input });
  const selected = selectedItems({ state, build, catalog });
  const authored = authoredBuildSkills({ input, selected });

  const observed: BuildPlan["observed"][number][] = selected.flatMap((item) => {
    if (!item.source) {
      return [];
    }

    return [
      {
        filePath: path.join(
          item.source.root.directory,
          item.source.relativePath,
        ),
        text: item.source.raw,
      },
    ];
  });

  const updates: FileUpdate[] = [];
  const warnings: string[] = [];
  const retained = new Set<string>();

  for (const item of authored) {
    if (item.owner === "provider") {
      warnings.push(
        `${item.title} is managed by its provider; use that harness to enable or disable it.`,
      );

      continue;
    }

    const published = await publishBuildSkill({
      ...options,
      state,
      build,
      item,
      text: input.edits[item.id] ?? item.text,
      edited: input.edits[item.id] !== undefined,
    });

    state = published.state;
    updates.push(...published.updates);
    warnings.push(...published.warnings);
    retained.add(item.id);
  }

  const retired = await retireBuildSkills({ state, build, retained });

  state = {
    ...retired.state,
    builds: [...state.builds.filter((entry) => entry.id !== build.id), build],
  };
  updates.push(...retired.updates);
  warnings.push(...retired.warnings);

  if (build.scope === "private") {
    warnings.push(
      "This repository overrides personal routing. Its harness can still discover globally installed skills. Shared repository requirements remain in force.",
    );
  }

  state = await recordBuildPreferences({ state, build });

  const native = await planBuildRouting({ ...options, state, build });

  state = native.state;
  updates.push(...native.updates);

  const filePath = environmentFile(options.paths);
  const previous = await readLocalText(filePath);

  observed.push(
    { filePath, text: previous },
    {
      filePath: options.paths.configFile,
      text: await readLocalText(options.paths.configFile),
    },
    {
      filePath: path.join(options.paths.shadowcloneDirectory, "skills.json"),
      text: await readLocalText(
        path.join(options.paths.shadowcloneDirectory, "skills.json"),
      ),
    },
  );

  if (options.paths.managedConfigFile) {
    observed.push({
      filePath: options.paths.managedConfigFile,
      text: await readLocalText(options.paths.managedConfigFile),
    });
  }

  updates.push({ filePath, previous, next: renderEnvironment(state) });

  const changed = updates.filter((update) => update.previous !== update.next);

  if (
    new Set(changed.map((update) => update.filePath)).size !== changed.length
  ) {
    throw new Error("The build contains overlapping destinations");
  }

  for (const update of changed) {
    if (update.filePath.includes(`${path.sep}.git${path.sep}`)) {
      throw new Error("Build output cannot modify Git metadata");
    }
  }

  return { input, state, updates: changed, warnings, observed };
}

export function buildPlanFingerprint(plan: BuildPlan): string {
  return fingerprint(
    JSON.stringify({ updates: plan.updates, observed: plan.observed }),
  );
}
