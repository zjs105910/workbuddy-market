import { proseExclusions } from "./exclusions";

function matchesAny(options: { readonly patterns: readonly string[]; readonly file: string }) {
  return options.patterns.some((pattern) => new Bun.Glob(pattern).match(options.file));
}

export function isProseFile(file: string): boolean {
  if (!file.endsWith(".md")) {
    return false;
  }

  if (matchesAny({ patterns: proseExclusions.kept, file })) {
    return true;
  }

  return !matchesAny({ patterns: proseExclusions.excluded, file });
}

export async function listProseFiles(options: {
  readonly rootDirectory: string;
}): Promise<readonly string[]> {
  const files: string[] = [];

  for await (const file of new Bun.Glob("**/*.md").scan({
    cwd: options.rootDirectory,
    onlyFiles: true,
    dot: true,
  })) {
    if (isProseFile(file)) {
      files.push(file);
    }
  }

  return files.sort();
}
