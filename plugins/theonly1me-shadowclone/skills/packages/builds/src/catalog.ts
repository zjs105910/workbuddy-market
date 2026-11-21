import path from "node:path";
import { canonicalPath, readEffectiveConfig, seedSkillsDirectory } from "@shadowclone/core";
import { type BuildContext, type BuildScope, readEnvironment } from "@shadowclone/environment";
import { loadSeedLibrary, discoverDeliverySkills, readMaintenanceState } from "@shadowclone/skills";
import { installedBuildItem } from "./installed";
import { customDocument } from "./selection";
import type { BuildItem } from "./types";
import { skillClassification } from "./classification";

export async function packagedBuildItems(): Promise<BuildItem[]> {
  const library = await loadSeedLibrary();
  const packaged = await seedSkillsDirectory();

  return Promise.all(
    library.guidance.map(async (entry) => ({
      id: entry.id,
      name: entry.id,
      title: entry.title,
      description:
        entry.kind === "skill"
          ? entry.description
          : entry.appliesWhen.join("; "),
      text:
        entry.kind === "skill"
          ? await Bun.file(path.join(packaged, entry.id, "SKILL.md")).text()
          : entry.body,
      kind: entry.kind,
      category: entry.category,
      section: entry.section,
      axis: entry.axis,
      alwaysOn: entry.kind === "skill" && entry.alwaysOn,
      owner: "packaged",
    })),
  );
}

export async function buildCatalog(
  context: BuildContext & { readonly scope?: BuildScope },
): Promise<readonly BuildItem[]> {
  const items = await packagedBuildItems();
  const environment = await readEnvironment(context.paths);

  const builds =
    environment?.builds
      .filter(
        (build) =>
          (build.scope === "global" && context.scope !== "shared") ||
          (build.scope === context.scope &&
            build.directory === canonicalPath(context.cwd)) ||
          (context.scope === "private" &&
            build.scope === "shared" &&
            build.directory === canonicalPath(context.cwd)),
      )
      .sort(
        (left, right) =>
          Number(left.scope !== "global") - Number(right.scope !== "global"),
      ) ?? [];

  for (const build of builds) {
    for (const custom of build.custom) {
      const id = `custom:${custom.name}`;

      if (!items.some((item) => item.id === id)) {
        items.push({
          id,
          name: custom.name,
          title: custom.name.replaceAll("-", " "),
          description: custom.description,
          text: build.edits[id] ?? customDocument(custom),
          kind: "skill",
          category: null,
          section: null,
          axis: null,
          alwaysOn: false,
          owner: "managed",
        });
      }
    }

    const artifacts =
      environment?.artifacts.filter(
        (artifact) =>
          artifact.buildId === build.id &&
          artifact.kind === "skill" &&
          artifact.buildEntryId !== "build-preferences",
      ) ?? [];

    for (const copies of Map.groupBy(
      artifacts,
      (artifact) => artifact.buildEntryId,
    ).values()) {
      const index = items.findIndex(
        (item) => item.id === copies[0]?.buildEntryId,
      );
      const installed = await installedBuildItem({
        build,
        artifacts: copies,
        original: items[index],
      });

      if (installed && index < 0) {
        items.push(installed);
      } else if (installed) {
        items[index] = installed;
      }
    }

    if (
      build.scope === context.scope ||
      (build.scope === "global" && context.scope === "private")
    ) {
      for (const [index, item] of items.entries()) {
        if (item.kind === "preference" && build.edits[item.id]) {
          items[index] = { ...item, text: build.edits[item.id] ?? item.text };
        }
      }
    }
  }

  const { config, policy } = await readEffectiveConfig({
    configPath: context.paths.configFile,
    managedConfigPath: context.paths.managedConfigFile,
  });

  if (!config.sources["skill-library"] || !policy.enabled) {
    return items;
  }

  const maintenance = await readMaintenanceState(context.paths);

  const roots = maintenance.roots.filter(
    (root) =>
      root.enabled &&
      (root.scope === "global" ||
        (context.scope !== "global" && root.cwd === context.cwd)),
  );

  const discovered = await discoverDeliverySkills(roots);

  for (const source of discovered.skills) {
    if (
      source.valid === false ||
      source.name === "shadowclone-baseline" ||
      environment?.artifacts.some(
        (artifact) => artifact.buildId && artifact.name === source.name,
      )
    ) {
      continue;
    }

    const classification = skillClassification(source.raw);

    items.push({
      id: source.id,
      name: source.name,
      title: source.name.replaceAll("-", " "),
      description: source.description,
      text: source.raw,
      kind: "skill",
      category: classification.category,
      section: classification.section,
      axis: classification.axis,
      alwaysOn: false,
      owner: source.root.owner === "user" ? "user" : "provider",
      source,
    });
  }

  return items;
}
