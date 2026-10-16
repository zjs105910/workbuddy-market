import type { BuildItem } from "@shadowclone/builds/browser";

const categories = ["testing", "review", "debugging", "planning", "writing", null] as const;
const plugins = ["typescript-kit", "frontend-studio", "release-tools"] as const;

function pluginSource(options: { readonly id: string; readonly plugin: string }): NonNullable<BuildItem["source"]> {
  return {
    id: options.id,
    root: {
      id: "0".repeat(64),
      directory: "/plugins",
      cwd: "/",
      scope: "global",
      owner: "third-party",
      destination: "/plugins",
      enabled: true,
    },
    relativePath: `publisher/${options.plugin}/2.1.0/skills/${options.id}/SKILL.md`,
    raw: "",
    redacted: "",
    fingerprint: "",
    name: options.id,
    description: "",
    body: "",
  };
}

export function syntheticLibrary(options: { readonly count: number }): {
  readonly items: readonly BuildItem[];
  readonly packagedIds: ReadonlySet<string>;
} {
  const items = Array.from({ length: options.count }, (_, index): BuildItem => {
    const id = `skill-${index}`;
    const plugin = index % 4 === 3 ? plugins[index % plugins.length] : undefined;

    return {
      id,
      name: id,
      title: `Synthetic skill with a long title ${index}`,
      description: `Synthetic behavior ${index}`,
      text: `Synthetic instructions ${index}`,
      kind: index % 9 === 8 ? "preference" : "skill",
      category: categories[index % categories.length] ?? null,
      section: "workflow",
      axis: null,
      alwaysOn: false,
      owner: plugin ? "provider" : "user",
      ...(plugin ? { source: pluginSource({ id, plugin }) } : {}),
    };
  });

  return {
    items,
    packagedIds: new Set(items.slice(0, 13).filter((item) => item.owner === "user").map((item) => item.id)),
  };
}
