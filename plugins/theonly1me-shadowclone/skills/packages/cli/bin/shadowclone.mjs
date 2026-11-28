#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const require = createRequire(import.meta.url);
const packageDirectory = path.dirname(
  path.dirname(fileURLToPath(import.meta.url)),
);
const bundle = path.join(packageDirectory, "dist", "shadowclone.js");

function bundledBunPath() {
  try {
    const manifestPath = require.resolve("bun/package.json");
    const manifest = require(manifestPath);
    const relative =
      typeof manifest.bin === "string" ? manifest.bin : manifest.bin?.bun;

    if (typeof relative !== "string") {
      return null;
    }

    const candidate = path.join(path.dirname(manifestPath), relative);

    return existsSync(candidate) ? candidate : null;
  } catch {
    return null;
  }
}

function bunOnPath() {
  return spawnSync("bun", ["--version"], { stdio: "ignore" }).status === 0
    ? "bun"
    : null;
}

const runtime = bundledBunPath() ?? bunOnPath();

if (runtime === null) {
  console.error(
    "shadowclone: bun was not found. Reinstall with npm i -g @shadowclone/cli, or install bun from https://bun.sh",
  );
  process.exit(1);
}

const result = spawnSync(runtime, [bundle, ...process.argv.slice(2)], {
  stdio: "inherit",
});

if (result.error) {
  console.error("shadowclone: could not start bun");
  process.exit(1);
}

process.exit(result.status ?? 1);
