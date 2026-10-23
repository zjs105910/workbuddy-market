import { chmodSync, copyFileSync, cpSync, existsSync, lstatSync, mkdirSync, readdirSync, readlinkSync, symlinkSync } from "node:fs";
import path from "node:path";
import { caseById } from "../cases";
import { runCommand } from "../fakeGh/git";
import { buildWorkspace } from "./build";

function copyExecutable(options: { readonly source: string; readonly target: string; readonly cwd: string }): void {
  mkdirSync(path.dirname(options.target), { recursive: true });

  if (runCommand({ command: ["cp", "-c", options.source, options.target], cwd: options.cwd }).exitCode !== 0) {
    copyFileSync(options.source, options.target);
  }

  chmodSync(options.target, 0o755);
}

function appleGit(cwd: string): string | null {
  const found = runCommand({ command: ["xcrun", "--find", "git"], cwd });
  const candidate = found.exitCode === 0 ? found.stdout.trim() : "/Library/Developer/CommandLineTools/usr/bin/git";

  return existsSync(candidate) && candidate !== "/usr/bin/git" ? candidate : null;
}

function installGit(options: { readonly workspace: string; readonly git: string }): void {
  const bin = path.join(options.workspace, "bin");
  const sourceCore = path.join(path.dirname(path.dirname(options.git)), "libexec", "git-core");
  const targetCore = path.join(bin, "git-core");

  copyExecutable({ source: options.git, target: path.join(bin, "git"), cwd: options.workspace });
  mkdirSync(targetCore, { recursive: true });

  for (const entry of readdirSync(sourceCore)) {
    const source = path.join(sourceCore, entry);
    const target = path.join(targetCore, entry);
    const metadata = lstatSync(source);

    if (metadata.isSymbolicLink() && path.basename(readlinkSync(source)) === "git") {
      symlinkSync("../git", target);
    } else if (metadata.isDirectory()) {
      cpSync(source, target, { recursive: true, dereference: true });
    } else if (!entry.startsWith("git-credential")) {
      cpSync(source, target, { dereference: true });
    }
  }
}

const [caseId, workspace, ghBinary] = process.argv.slice(2);

if (caseId === undefined || workspace === undefined || ghBinary === undefined) {
  throw new Error("usage: cli.ts <case-id> <workspace> <compiled-gh>");
}

buildWorkspace({ root: workspace, definition: caseById(caseId) });
copyExecutable({ source: ghBinary, target: path.join(workspace, "bin", "gh"), cwd: workspace });

const git = appleGit(workspace);

if (git !== null) {
  installGit({ workspace, git });
}
