import { z } from "zod";
import type { Stack, StackContext } from "../types";

const javascriptSource = /\.(?:[cm]?[jt]sx?|vue|svelte)$/;
const typecheckScripts = ["typecheck", "type-check", "check-types", "tsc"] as const;
const eslintConfigs = [
  "eslint.config.js",
  "eslint.config.mjs",
  "eslint.config.cjs",
  "eslint.config.ts",
  "eslint.config.mts",
  ".eslintrc",
  ".eslintrc.js",
  ".eslintrc.cjs",
  ".eslintrc.json",
  ".eslintrc.yml",
  ".eslintrc.yaml",
] as const;

const packageSchema = z.object({ scripts: z.record(z.string(), z.string()).optional() });

function packageManager(context: StackContext): "bun" | "pnpm" | "yarn" | "npm" {
  if (context.exists("bun.lock") || context.exists("bun.lockb")) {
    return "bun";
  }

  if (context.exists("pnpm-lock.yaml")) {
    return "pnpm";
  }

  return context.exists("yarn.lock") ? "yarn" : "npm";
}

function parsePackage(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

function typecheckScript(context: StackContext): string | null {
  const parsed = packageSchema.safeParse(parsePackage(context.read("package.json")));
  const scripts = parsed.success ? (parsed.data.scripts ?? {}) : {};

  return typecheckScripts.find((name) => scripts[name] !== undefined) ?? null;
}

function changedSources(context: StackContext): readonly string[] {
  return context.changedFiles.filter((file) => javascriptSource.test(file) && context.exists(file));
}

export const javascriptStack: Stack = {
  id: "javascript",
  sources: /\.(?:[cm]?[jt]sx?|vue|svelte|json)$/,
  detect: (context) => context.exists("package.json"),
  install: (context) => {
    const manager = packageManager(context);

    if (manager === "bun") {
      return ["bun", "install", "--frozen-lockfile", "--ignore-scripts"];
    }

    if (manager === "pnpm") {
      return ["pnpm", "install", "--frozen-lockfile", "--ignore-scripts"];
    }

    if (manager === "yarn") {
      return context.exists(".yarnrc.yml")
        ? ["yarn", "install", "--immutable", "--mode=skip-build"]
        : ["yarn", "install", "--frozen-lockfile", "--ignore-scripts", "--non-interactive"];
    }

    return context.exists("package-lock.json")
      ? ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"]
      : ["npm", "install", "--ignore-scripts", "--no-audit", "--no-fund"];
  },
  commands: [
    {
      tool: "typecheck",
      scope: "new-in-head",
      parser: "paren",
      command: (context) => {
        const script = typecheckScript(context);

        if (script !== null) {
          return [packageManager(context), "run", script];
        }

        return context.exists("tsconfig.json") && context.exists("node_modules/.bin/tsc")
          ? ["node_modules/.bin/tsc", "--noEmit", "--pretty", "false", "-p", "tsconfig.json"]
          : null;
      },
    },
    {
      tool: "eslint",
      scope: "changed-lines",
      parser: "eslint-json",
      command: (context) => {
        const files = changedSources(context);
        const configured = eslintConfigs.some((config) => context.exists(config));

        return configured && files.length > 0 && context.exists("node_modules/.bin/eslint")
          ? ["node_modules/.bin/eslint", "--format", "json", ...files]
          : null;
      },
    },
    {
      tool: "biome",
      scope: "changed-lines",
      parser: "github",
      command: (context) => {
        const files = changedSources(context);
        const configured = context.exists("biome.json") || context.exists("biome.jsonc");

        return configured && files.length > 0 && context.exists("node_modules/.bin/biome")
          ? ["node_modules/.bin/biome", "lint", "--reporter=github", ...files]
          : null;
      },
    },
  ],
};
