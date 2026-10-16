import path from "node:path";
import { z } from "zod";
import type { Diagnostic, ParserId } from "./types";

type RawDiagnostic = { readonly path: string; readonly line: number; readonly message: string };

const linePatterns: Readonly<Record<Exclude<ParserId, "eslint-json" | "file-list" | "gradle">, RegExp>> = {
  colon: /^(?<path>[^\s:][^:]*):(?<line>\d+)(?::\d+)?:\s*(?<message>.+)$/,
  paren: /^(?<path>[^\s(][^(]*)\((?<line>\d+)(?:,\d+)*\):\s*(?<message>.+?)(?:\s+\[[^\]]+\])?$/,
  maven: /^\[(?:ERROR|WARNING)\]\s+(?<path>[^:[\]]+?):\[(?<line>\d+),\d+\]\s*(?<message>.+)$/,
  github: /^::(?:error|warning)\s[^:]*?file=(?<path>[^,]+),line=(?<line>\d+)[^:]*::(?<message>.+)$/,
  pyright: /^\s*(?<path>\S[^:]*):(?<line>\d+):\d+\s+-\s+(?<message>.+)$/,
};

const kotlinPattern = /^[ew]:\s+(?:file:\/\/)?(?<path>[^:]+):(?<line>\d+):\d+\s+(?<message>.+)$/;

const eslintSchema = z.array(
  z.object({
    filePath: z.string(),
    messages: z.array(
      z.object({
        line: z.number().optional(),
        message: z.string(),
        ruleId: z.string().nullable().optional(),
      }),
    ),
  }),
);

function matchLines(options: { readonly output: string; readonly patterns: readonly RegExp[] }): readonly RawDiagnostic[] {
  return options.output.split("\n").flatMap((line) => {
    for (const pattern of options.patterns) {
      const groups = pattern.exec(line.trimEnd())?.groups;

      if (groups?.path && groups.line && groups.message) {
        return [{ path: groups.path, line: Number(groups.line), message: groups.message }];
      }
    }

    return [];
  });
}

function parseEslint(output: string): readonly RawDiagnostic[] {
  const start = output.indexOf("[");
  const parsed = eslintSchema.safeParse(JSON.parse(start < 0 ? "[]" : output.slice(start)));

  if (!parsed.success) {
    return [];
  }

  return parsed.data.flatMap((file) =>
    file.messages.map((message) => ({
      path: file.filePath,
      line: message.line ?? 0,
      message: message.ruleId ? `${message.message} (${message.ruleId})` : message.message,
    })),
  );
}

function rawDiagnostics(options: { readonly parser: ParserId; readonly output: string }): readonly RawDiagnostic[] {
  const { parser, output } = options;

  if (parser === "eslint-json") {
    return parseEslint(output);
  }

  if (parser === "file-list") {
    return output
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.length > 0)
      .map((line) => ({ path: line, line: 1, message: "The file does not match the formatter's output." }));
  }

  if (parser === "gradle") {
    return matchLines({ output, patterns: [kotlinPattern, linePatterns.colon] });
  }

  return matchLines({ output, patterns: [linePatterns[parser]] });
}

export function relativeToRoot(options: { readonly filePath: string; readonly roots: readonly string[] }): string | null {
  const withoutScheme = options.filePath.replace(/^file:\/\//, "");

  if (!path.isAbsolute(withoutScheme)) {
    const normalized = path.posix.normalize(withoutScheme.replaceAll("\\", "/"));

    return normalized.startsWith("../") ? null : normalized.replace(/^\.\//, "");
  }

  for (const root of options.roots) {
    const relative = path.relative(root, withoutScheme);

    if (!relative.startsWith("..") && !path.isAbsolute(relative)) {
      return relative.split(path.sep).join("/");
    }
  }

  return null;
}

export function parseDiagnostics(options: {
  readonly tool: string;
  readonly parser: ParserId;
  readonly output: string;
  readonly roots: readonly string[];
}): readonly Diagnostic[] {
  return rawDiagnostics({ parser: options.parser, output: options.output }).flatMap((raw) => {
    const relative = relativeToRoot({ filePath: raw.path.trim(), roots: options.roots });

    return relative !== null && raw.line > 0
      ? [{ tool: options.tool, path: relative, line: raw.line, message: raw.message.trim() }]
      : [];
  });
}
