import path from "node:path";
import { readHarnessManifest } from "../environment/harness/manifest";

const maximumAncestors = 32;

export async function committedHarnessRuleKeys(
  cwd: string,
): Promise<ReadonlySet<string>> {
  let directory = path.resolve(cwd);

  for (let depth = 0; depth < maximumAncestors; depth += 1) {
    if (
      await Bun.file(
        path.join(directory, ".shadowclone", "harness.json"),
      ).exists()
    ) {
      const manifest = await readHarnessManifest(directory).catch(() => null);

      return new Set(manifest?.ruleKeys ?? []);
    }

    const parent = path.dirname(directory);

    if (parent === directory) {
      break;
    }

    directory = parent;
  }

  return new Set();
}
