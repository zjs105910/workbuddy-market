import { spawnSync } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const minimumCliVersion = "0.0.13";

export function cliCompatibility(version) {
  const current = typeof version === "string" ? version.trim() : null;
  const stable = current?.match(/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/);
  const required = minimumCliVersion.split(".").map(Number);
  let compatible = stable !== null && stable !== undefined;

  if (stable) {
    for (const [index, component] of stable.slice(1).entries()) {
      const minimum = required[index];
      if (minimum === undefined) throw new Error("Invalid minimum CLI version");
      const installed = Number(component);
      if (installed !== minimum) {
        compatible = installed > minimum;
        break;
      }
    }
  }

  return {
    version: stable ? current : null,
    minimumVersion: minimumCliVersion,
    status: compatible ? "ready" : stable ? "outdated" : "unavailable",
  };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const result = spawnSync("shadowclone", ["--version"], {
    encoding: "utf8", timeout: 10_000, maxBuffer: 4096,
  });
  console.log(JSON.stringify(cliCompatibility(result.status === 0 ? result.stdout : null)));
}
