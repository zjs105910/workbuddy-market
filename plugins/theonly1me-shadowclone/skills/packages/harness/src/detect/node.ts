import { z } from "zod";
import { toolPatterns, type KnownTool } from "@shadowclone/profile";
import type { NodeFacts, NodePackageManager } from "../types";

const packageSchema = z.object({
  scripts: z.record(z.string(), z.string()).optional(),
  dependencies: z.record(z.string(), z.string()).optional(),
  devDependencies: z.record(z.string(), z.string()).optional(),
  packageManager: z.string().optional(),
});

const lockfileManagers: readonly (readonly [string, NodePackageManager])[] = [
  ["bun.lock", "bun"],
  ["bun.lockb", "bun"],
  ["pnpm-lock.yaml", "pnpm"],
  ["yarn.lock", "yarn"],
  ["package-lock.json", "npm"],
];

const dependencyTools: readonly (readonly [string, KnownTool])[] = [
  ["typescript", "typescript"],
  ["jest", "jest"],
  ["vitest", "vitest"],
  ["mocha", "mocha"],
  ["eslint", "eslint"],
  ["prettier", "prettier"],
  ["@biomejs/biome", "biome"],
  ["react", "react"],
  ["nx", "nx"],
  ["@types/bun", "bun"],
];

const configTools: readonly (readonly [RegExp, KnownTool])[] = [
  [/^tsconfig(\..+)?\.json$/, "typescript"],
  [/^biome\.jsonc?$/, "biome"],
  [/^(\.eslintrc(\..+)?|eslint\.config\..+)$/, "eslint"],
  [/^(\.prettierrc(\..+)?|prettier\.config\..+)$/, "prettier"],
  [/^jest\.config\..+$/, "jest"],
  [/^vitest\.config\..+$/, "vitest"],
  [/^nx\.json$/, "nx"],
];

function packageManager(options: {
  readonly entries: readonly string[];
  readonly declared: string | undefined;
}): NodePackageManager {
  const fromLockfile = lockfileManagers.find(([lockfile]) =>
    options.entries.includes(lockfile),
  );

  if (fromLockfile) {
    return fromLockfile[1];
  }

  const declared = options.declared?.split("@")[0];

  return declared === "bun" || declared === "pnpm" || declared === "yarn"
    ? declared
    : "npm";
}

export function detectNode(options: {
  readonly entries: readonly string[];
  readonly packageText: string;
}): { readonly facts: NodeFacts; readonly tools: readonly KnownTool[] } {
  let parsedJson: unknown;

  try {
    parsedJson = JSON.parse(options.packageText);
  } catch {
    throw new Error("package.json could not be parsed");
  }

  const parsed = packageSchema.safeParse(parsedJson);
  const manifest = parsed.success ? parsed.data : {};
  const scripts = manifest.scripts ?? {};

  const dependencies = new Set([
    ...Object.keys(manifest.dependencies ?? {}),
    ...Object.keys(manifest.devDependencies ?? {}),
  ]);

  const manager = packageManager({
    entries: options.entries,
    declared: manifest.packageManager,
  });

  const scriptText = Object.values(scripts).join("\n");
  const tools = new Set<KnownTool>([manager]);

  for (const [dependency, tool] of dependencyTools) {
    if (dependencies.has(dependency)) {
      tools.add(tool);
    }
  }

  for (const [pattern, tool] of configTools) {
    if (options.entries.some((entry) => pattern.test(entry))) {
      tools.add(tool);
    }
  }

  for (const [tool, pattern] of Object.entries(toolPatterns)) {
    if (pattern.test(scriptText)) {
      tools.add(knownTool(tool));
    }
  }

  return { facts: { packageManager: manager, scripts }, tools: [...tools] };
}

function knownTool(name: string): KnownTool {
  const tool = Object.keys(toolPatterns).find(
    (candidate): candidate is KnownTool => candidate === name,
  );

  if (tool === undefined) {
    throw new Error("Unknown tool name");
  }

  return tool;
}
