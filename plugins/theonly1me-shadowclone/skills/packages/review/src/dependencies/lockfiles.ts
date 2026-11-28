import path from "node:path";
import { parseBunLock, parsePackageLock, parsePnpmLock, parseYarnLock } from "./javascriptLockfiles";
import {
  parseCargoLock,
  parseComposerLock,
  parseGemfileLock,
  parseGoModule,
  parseNugetLock,
  parsePythonLock,
  parseRequirements,
} from "./otherLockfiles";
import type { LockedPackage } from "./types";

type LockfileParser = (text: string) => readonly LockedPackage[];

const parsersByFileName: Readonly<Record<string, LockfileParser>> = {
  "package-lock.json": parsePackageLock,
  "npm-shrinkwrap.json": parsePackageLock,
  "bun.lock": parseBunLock,
  "yarn.lock": parseYarnLock,
  "pnpm-lock.yaml": parsePnpmLock,
  "poetry.lock": parsePythonLock,
  "uv.lock": parsePythonLock,
  "Cargo.lock": parseCargoLock,
  "go.mod": parseGoModule,
  "Gemfile.lock": parseGemfileLock,
  "composer.lock": parseComposerLock,
  "packages.lock.json": parseNugetLock,
};

export function lockfileParser(filePath: string): LockfileParser | null {
  const name = path.posix.basename(filePath);

  if (/^requirements[\w.-]*\.txt$/.test(name)) {
    return parseRequirements;
  }

  return parsersByFileName[name] ?? null;
}
