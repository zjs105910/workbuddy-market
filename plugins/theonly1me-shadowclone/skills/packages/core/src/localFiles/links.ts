import { existsSync, lstatSync, readlinkSync, realpathSync } from "node:fs";
import path from "node:path";

export function realPathOrNull(filePath: string): string | null {
  try {
    return realpathSync(filePath);
  } catch {
    return null;
  }
}

export function firstLink(filePath: string): { readonly path: string; readonly target: string } | null {
  let current = path.resolve(filePath);

  for (;;) {
    if (lstatSync(current, { throwIfNoEntry: false })?.isSymbolicLink()) {
      return { path: current, target: readlinkSync(current) };
    }

    const parent = path.dirname(current);

    if (parent === current) return null;

    current = parent;
  }
}

export function resolvedPath(filePath: string): string {
  const missing: string[] = [];
  let current = path.resolve(filePath);

  while (!existsSync(current)) {
    const parent = path.dirname(current);

    if (parent === current) return path.resolve(filePath);

    missing.unshift(path.basename(current));
    current = parent;
  }

  return path.join(realPathOrNull(current) ?? current, ...missing);
}

export function linkedHomeFile(options: { readonly filePath: string; readonly homeDirectory: string }): string | null {
  if (!lstatSync(options.filePath, { throwIfNoEntry: false })?.isSymbolicLink()) return null;

  const target = realPathOrNull(options.filePath);
  const home = realPathOrNull(options.homeDirectory);

  if (target === null || home === null || !lstatSync(target).isFile()) return null;

  const relative = path.relative(home, target);

  return relative !== "" && !relative.startsWith("..") && !path.isAbsolute(relative) ? target : null;
}
