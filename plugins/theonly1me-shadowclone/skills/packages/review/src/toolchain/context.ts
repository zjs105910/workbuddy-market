import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import type { StackContext } from "./types";

export function stackContext(options: {
  readonly root: string;
  readonly changedFiles: readonly string[];
}): StackContext {
  return {
    root: options.root,
    changedFiles: options.changedFiles,
    exists: (relativePath) => existsSync(path.join(options.root, relativePath)),
    read: (relativePath) => {
      try {
        return readFileSync(path.join(options.root, relativePath), "utf8");
      } catch {
        return "";
      }
    },
  };
}
