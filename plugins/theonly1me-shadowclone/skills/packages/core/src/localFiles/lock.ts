import { Database } from "bun:sqlite";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { assertRegularDestination } from "./index";

export async function acquireLocalLock(
  filePath: string,
): Promise<{ readonly release: () => void } | null> {
  assertRegularDestination(filePath);
  await mkdir(path.dirname(filePath), { recursive: true });

  const database = new Database(filePath, { create: true });

  try {
    database.exec("PRAGMA busy_timeout = 0");
    database.exec("BEGIN IMMEDIATE");
  } catch {
    database.close();

    return null;
  }

  return {
    release: () => {
      database.exec("ROLLBACK");
      database.close();
    },
  };
}
