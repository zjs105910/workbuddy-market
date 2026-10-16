import toml from "smol-toml";
import { z } from "zod";
import type { Ecosystem, LockedPackage } from "./types";

function parseToml(text: string): unknown {
  try {
    return toml.parse(text);
  } catch {
    return null;
  }
}

const tomlPackagesSchema = z.object({
  package: z.array(z.object({ name: z.string(), version: z.string(), source: z.unknown().optional() })).optional(),
});

function tomlPackages(options: {
  readonly text: string;
  readonly ecosystem: Ecosystem;
  readonly fromRegistry: (source: unknown) => boolean;
}): readonly LockedPackage[] {
  const parsed = tomlPackagesSchema.safeParse(parseToml(options.text));

  return parsed.success
    ? (parsed.data.package ?? [])
        .filter((entry) => options.fromRegistry(entry.source))
        .map((entry) => ({ ecosystem: options.ecosystem, name: entry.name, version: entry.version }))
    : [];
}

export function parsePythonLock(text: string): readonly LockedPackage[] {
  return tomlPackages({
    text,
    ecosystem: "PyPI",
    fromRegistry: (source) => typeof source !== "object" || source === null || "registry" in source,
  });
}

export function parseCargoLock(text: string): readonly LockedPackage[] {
  return tomlPackages({
    text,
    ecosystem: "crates.io",
    fromRegistry: (source) => typeof source === "string" && source.startsWith("registry+"),
  });
}

export function parseRequirements(text: string): readonly LockedPackage[] {
  return text.split("\n").flatMap((line) => {
    const match = /^([A-Za-z0-9][A-Za-z0-9_.-]*)(?:\[[^\]]*\])?\s*==\s*([^\s;#,]+)/.exec(line.trim());

    return match?.[1] && match[2] ? [{ ecosystem: "PyPI" as const, name: match[1], version: match[2] }] : [];
  });
}

export function parseGoModule(text: string): readonly LockedPackage[] {
  return text.split("\n").flatMap((line) => {
    const match = /^\s*(?:require\s+)?([a-z0-9][\w.-]*\.[a-z]{2,}\/[^\s]+)\s+(v\d+\.\d+\.\d+[^\s]*)/.exec(line);

    return match?.[1] && match[2] ? [{ ecosystem: "Go" as const, name: match[1], version: match[2] }] : [];
  });
}

export function parseGemfileLock(text: string): readonly LockedPackage[] {
  return text.split("\n").flatMap((line) => {
    const match = /^ {4}([A-Za-z0-9_.-]+) \((\d[^)\s-]*)(?:-[^)]+)?\)$/.exec(line);

    return match?.[1] && match[2] ? [{ ecosystem: "RubyGems" as const, name: match[1], version: match[2] }] : [];
  });
}

const composerSchema = z.object({
  packages: z.array(z.object({ name: z.string(), version: z.string() })).optional(),
  "packages-dev": z.array(z.object({ name: z.string(), version: z.string() })).optional(),
});

const nugetSchema = z.object({
  dependencies: z.record(z.string(), z.record(z.string(), z.object({ resolved: z.string().optional(), type: z.string().optional() }))),
});

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function parseComposerLock(text: string): readonly LockedPackage[] {
  const parsed = composerSchema.safeParse(parseJson(text));

  return parsed.success
    ? [...(parsed.data.packages ?? []), ...(parsed.data["packages-dev"] ?? [])].map((entry) => ({
        ecosystem: "Packagist" as const,
        name: entry.name,
        version: entry.version.replace(/^v/, ""),
      }))
    : [];
}

export function parseNugetLock(text: string): readonly LockedPackage[] {
  const parsed = nugetSchema.safeParse(parseJson(text));

  return parsed.success
    ? Object.values(parsed.data.dependencies).flatMap((framework) =>
        Object.entries(framework).flatMap(([name, entry]) =>
          entry.resolved && entry.type !== "Project" ? [{ ecosystem: "NuGet" as const, name, version: entry.resolved }] : [],
        ),
      )
    : [];
}
