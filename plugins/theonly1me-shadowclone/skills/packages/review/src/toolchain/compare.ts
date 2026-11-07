import type { DiffFile } from "../collect";
import type { Diagnostic, DiagnosticScope } from "./types";

function diagnosticKey(diagnostic: Diagnostic): string {
  return `${diagnostic.tool}|${diagnostic.path}|${diagnostic.message.replace(/\d+/g, "#")}`;
}

export function subtractBase(options: {
  readonly head: readonly Diagnostic[];
  readonly base: readonly Diagnostic[];
}): readonly Diagnostic[] {
  const remaining = new Map<string, number>();

  for (const diagnostic of options.base) {
    const key = diagnosticKey(diagnostic);
    remaining.set(key, (remaining.get(key) ?? 0) + 1);
  }

  return options.head.filter((diagnostic) => {
    const key = diagnosticKey(diagnostic);
    const count = remaining.get(key) ?? 0;

    if (count === 0) {
      return true;
    }

    remaining.set(key, count - 1);
    return false;
  });
}

export function limitToChanges(options: {
  readonly diagnostics: readonly Diagnostic[];
  readonly files: readonly DiffFile[];
  readonly scope: Exclude<DiagnosticScope, "new-in-head">;
}): readonly Diagnostic[] {
  const addedLines = new Map(
    options.files.map((file) => [file.path, new Set(file.added.map((added) => added.line))]),
  );

  return options.diagnostics.filter((diagnostic) => {
    const lines = addedLines.get(diagnostic.path);

    return lines !== undefined && (options.scope === "changed-files" || lines.has(diagnostic.line));
  });
}
