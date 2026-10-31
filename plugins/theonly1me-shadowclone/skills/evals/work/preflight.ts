import { existsSync, lstatSync, readdirSync } from "node:fs";
import os from "node:os";
import path from "node:path";

function symbolicLinks(options: { readonly directory: string; readonly depth: number }): readonly string[] {
  if (options.depth < 0 || !existsSync(options.directory)) {
    return [];
  }

  return readdirSync(options.directory).flatMap((entry) => {
    const target = path.join(options.directory, entry);
    const metadata = lstatSync(target);

    if (metadata.isSymbolicLink()) {
      return [target];
    }

    return metadata.isDirectory() ? symbolicLinks({ directory: target, depth: options.depth - 1 }) : [];
  });
}

export function dockerConfigLinks(): readonly string[] {
  return symbolicLinks({ directory: process.env.DOCKER_CONFIG ?? path.join(os.homedir(), ".docker"), depth: 4 });
}

export function dockerLinksMessage(links: readonly string[]): string {
  const folders = [...new Set(links.map((link) => path.dirname(link)))];

  return [
    `claude plugin eval refuses Bash-granting runs while ${path.join(os.homedir(), ".docker")} contains symbolic links (${links.length} found).`,
    "Move these folders aside for the run and restore them afterwards:",
    ...folders.map((folder) => `  ${folder}`),
    "Pass --skip-docker-check to run anyway.",
  ].join("\n");
}
