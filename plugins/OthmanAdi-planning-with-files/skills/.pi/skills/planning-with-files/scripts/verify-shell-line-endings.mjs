#!/usr/bin/env node

import { readdir, readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const defaultPackageRoot = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "..",
);
const packageRoot = process.argv[2]
  ? resolve(process.argv[2])
  : defaultPackageRoot;
const scriptsRoot = resolve(packageRoot, "scripts");

async function verifyShellLineEndings() {
  const entries = await readdir(scriptsRoot, { withFileTypes: true });
  const shellScripts = entries
    .filter((entry) => entry.name.endsWith(".sh"))
    .map((entry) => entry.name)
    .sort();

  if (shellScripts.length === 0) {
    throw new Error("No shell scripts found under scripts/*.sh");
  }

  const offenders = [];
  for (const filename of shellScripts) {
    const contents = await readFile(resolve(scriptsRoot, filename));
    if (contents.includes(0x0d)) {
      offenders.push(`scripts/${filename}`);
    }
  }

  if (offenders.length > 0) {
    throw new Error(
      `Shell scripts contain carriage-return bytes:\n${offenders
        .map((filename) => `- ${filename}`)
        .join("\n")}`,
    );
  }
}

try {
  await verifyShellLineEndings();
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(message);
  process.exitCode = 1;
}
