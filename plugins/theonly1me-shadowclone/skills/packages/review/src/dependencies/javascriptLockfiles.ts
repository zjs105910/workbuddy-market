import { z } from "zod";
import type { LockedPackage } from "./types";

const exactVersion = /^\d+\.\d+\.\d+(?:[-+][\w.-]+)?$/;

function npmPackage(options: { readonly name: string; readonly version: unknown }): readonly LockedPackage[] {
  const version = typeof options.version === "string" ? options.version : "";

  return options.name.length > 0 && exactVersion.test(version) ? [{ ecosystem: "npm", name: options.name, version }] : [];
}

function parseJson(text: string): unknown {
  try {
    return JSON.parse(text.replace(/,(\s*[}\]])/g, "$1"));
  } catch {
    return null;
  }
}

const packageLockSchema = z.object({
  packages: z.record(z.string(), z.object({ version: z.unknown().optional(), link: z.boolean().optional() })).optional(),
});

export function parsePackageLock(text: string): readonly LockedPackage[] {
  const parsed = packageLockSchema.safeParse(parseJson(text));

  if (!parsed.success) {
    return [];
  }

  return Object.entries(parsed.data.packages ?? {}).flatMap(([location, entry]) => {
    const name = location.split("node_modules/").at(-1) ?? "";

    return location === "" || entry.link === true ? [] : npmPackage({ name, version: entry.version });
  });
}

const bunLockSchema = z.object({ packages: z.record(z.string(), z.array(z.unknown())).optional() });

export function parseBunLock(text: string): readonly LockedPackage[] {
  const parsed = bunLockSchema.safeParse(parseJson(text));

  if (!parsed.success) {
    return [];
  }

  return Object.values(parsed.data.packages ?? {}).flatMap(([specification]) => {
    if (typeof specification !== "string") {
      return [];
    }

    const separator = specification.lastIndexOf("@");

    return separator > 0 ? npmPackage({ name: specification.slice(0, separator), version: specification.slice(separator + 1) }) : [];
  });
}

export function parseYarnLock(text: string): readonly LockedPackage[] {
  const packages: LockedPackage[] = [];
  let name: string | null = null;

  for (const line of text.split("\n")) {
    if (/^\S.*:$/.test(line) && !line.startsWith("#") && !line.startsWith("__metadata")) {
      const [first = ""] = line.slice(0, -1).split(",");
      const specification = first.trim().replace(/^"|"$/g, "").replace("@npm:", "@");
      const separator = specification.lastIndexOf("@");

      name = separator > 0 ? specification.slice(0, separator) : null;
      continue;
    }

    const version = /^\s+version:?\s+"?([^"\s]+)"?\s*$/.exec(line)?.[1];

    if (name !== null && version !== undefined) {
      packages.push(...npmPackage({ name, version }));
      name = null;
    }
  }

  return packages;
}

export function parsePnpmLock(text: string): readonly LockedPackage[] {
  return text.split("\n").flatMap((line) => {
    const match = /^ {2}'?\/?((?:@[^/@\s']+\/)?[^@\s'(/]+)@([^(:'\s]+)/.exec(line);

    return match?.[1] && match[2] ? npmPackage({ name: match[1], version: match[2] }) : [];
  });
}
