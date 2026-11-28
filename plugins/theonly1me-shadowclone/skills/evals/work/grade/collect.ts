import { chmodSync, cpSync, existsSync, mkdirSync, readdirSync, readFileSync, rmSync } from "node:fs";
import path from "node:path";
import { runGit } from "../fakeGh/git";

function findStateDirectory(directory: string, depth: number): string | null {
  if (depth < 0 || !existsSync(directory)) {
    return null;
  }

  if (existsSync(path.join(directory, ".fake-gh", "state.json"))) {
    return path.join(directory, ".fake-gh");
  }

  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.isDirectory() && !entry.isSymbolicLink() && entry.name !== ".git" && entry.name !== "node_modules") {
      const found = findStateDirectory(path.join(directory, entry.name), depth - 1);

      if (found !== null) {
        return found;
      }
    }
  }

  return null;
}

export function unsealKeptRun(keptDirectory: string): void {
  chmodSync(keptDirectory, 0o700);

  const sealed = path.join(keptDirectory, "sealed");

  if (existsSync(sealed)) {
    chmodSync(sealed, 0o700);
  }
}

export function copyForGrading(options: {
  readonly keptDirectory: string;
  readonly target: string;
}): string | null {
  unsealKeptRun(options.keptDirectory);

  const stateDirectory = findStateDirectory(path.join(options.keptDirectory, "sealed"), 4) ?? findStateDirectory(options.keptDirectory, 4);

  if (stateDirectory === null) {
    return null;
  }

  const target = path.join(options.target, ".fake-gh");
  const remote = path.join(target, "remote.git");

  rmSync(options.target, { recursive: true, force: true });
  mkdirSync(target, { recursive: true });
  cpSync(path.join(stateDirectory, "state.json"), path.join(target, "state.json"));
  cpSync(path.join(stateDirectory, "log.jsonl"), path.join(target, "log.jsonl"));
  runGit({ cwd: target, args: ["init", "--quiet", "--bare", remote] });

  const source = path.join(stateDirectory, "remote.git");

  cpSync(path.join(source, "objects"), path.join(remote, "objects"), { recursive: true });
  cpSync(path.join(source, "refs"), path.join(remote, "refs"), { recursive: true });

  if (existsSync(path.join(source, "packed-refs"))) {
    cpSync(path.join(source, "packed-refs"), path.join(remote, "packed-refs"));
  }

  return options.target;
}

export function readTrace(tracePath: string): string {
  return existsSync(tracePath) ? readFileSync(tracePath, "utf8") : "";
}
