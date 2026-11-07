import path from "node:path";
import { commitLocalChanges } from "@shadowclone/changes";
import { acquireLocalLock } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import type { HarnessPlan } from "./plan";
import { recordHarnessRoot } from "./state";

export async function applyHarness(options: {
  readonly paths: ProjectPaths;
  readonly plan: HarnessPlan;
}): Promise<string | null> {
  const lock = await acquireLocalLock(
    path.join(options.paths.shadowcloneDirectory, "harness-write.db"),
  );

  if (!lock) {
    throw new Error("Another harness update is running; retry shortly");
  }

  try {
    const updates = options.plan.files.flatMap((file) =>
      (file.status === "create" || file.status === "update") &&
      file.next !== null
        ? [
            {
              filePath: path.join(options.plan.root, file.relativePath),
              previous: file.previous,
              next: file.next,
            },
          ]
        : [],
    );

    await recordHarnessRoot({ paths: options.paths, root: options.plan.root });

    return await commitLocalChanges({
      paths: options.paths,
      root: options.plan.root,
      kind: "harness",
      updates,
    });
  } finally {
    lock.release();
  }
}
