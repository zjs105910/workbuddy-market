import { open, rm } from "node:fs/promises";
import path from "node:path";
import { ownedDirectory } from "@shadowclone/core";

export async function lockEvaluation(
  directory: string,
): Promise<() => Promise<void>> {
  await ownedDirectory(directory);

  const filePath = path.join(directory, ".running");
  const handle = await open(filePath, "wx", 0o600).catch(() => {
    throw new Error(
      "Evaluation is running or has an interrupted lock. Confirm the prior process ended before removing .running from this evaluation's private directory; keep its budget ledger.",
    );
  });

  try {
    await handle.writeFile(String(process.pid));
  } catch (error) {
    await rm(filePath, { force: true });

    throw error;
  } finally {
    await handle.close();
  }

  return () => rm(filePath, { force: true });
}
