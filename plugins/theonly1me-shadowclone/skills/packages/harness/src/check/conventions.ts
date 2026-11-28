import type { CommentReader, SourceComment } from "./comments";
import type { HarnessFinding } from "./types";
import type { Convention } from "@shadowclone/environment";

const proseExtensions = [
  ".md",
  ".mdx",
  ".txt",
  ".yml",
  ".yaml",
  ".json",
  ".toml",
] as const;
const scriptExtensions = [
  ".ts",
  ".tsx",
  ".mts",
  ".cts",
  ".js",
  ".jsx",
  ".mjs",
  ".cjs",
] as const;
const typescriptExtensions = [".ts", ".tsx", ".mts", ".cts"] as const;
const suppressionPattern =
  /eslint-disable|@ts-(?:ignore|expect-error|nocheck)|biome-ignore|\bnoqa\b|type:\s*ignore|\bnolint\b|pylint:\s*disable|#!?\[allow\(/i;

export function fileExtension(filePath: string): string {
  const name = filePath.split("/").at(-1) ?? "";
  const dot = name.lastIndexOf(".");

  return dot <= 0 ? "" : name.slice(dot).toLowerCase();
}

function countLines(text: string): number {
  if (text === "") {
    return 0;
  }

  const lineCount = text.split("\n").length;

  return text.endsWith("\n") ? lineCount - 1 : lineCount;
}

function matchingLines(options: {
  readonly text: string;
  readonly test: (line: string) => boolean;
}): readonly number[] {
  return options.text
    .split("\n")
    .flatMap((line, index) => (options.test(line) ? [index + 1] : []));
}

function suppressionLines(options: {
  readonly text: string;
  readonly comments: readonly SourceComment[] | null;
}): readonly number[] {
  if (options.comments !== null) {
    return options.comments
      .filter((comment) => suppressionPattern.test(comment.text))
      .map((comment) => comment.line);
  }

  return matchingLines({
    text: options.text,
    test: (line) => suppressionPattern.test(line),
  });
}

export function conventionFindings(options: {
  readonly path: string;
  readonly text: string;
  readonly conventions: readonly Convention[];
  readonly sourceExtensions: readonly string[];
  readonly readComments: CommentReader | null;
}): readonly HarnessFinding[] {
  const extension = fileExtension(options.path);
  const isSource = options.sourceExtensions.includes(extension);
  const isScript = scriptExtensions.some(
    (candidate) => candidate === extension,
  );
  const isTypescript = typescriptExtensions.some(
    (candidate) => candidate === extension,
  );
  const isProse = proseExtensions.some((candidate) => candidate === extension);

  const comments =
    isScript && options.readComments !== null
      ? options.readComments({
          text: options.text,
          jsx: extension.endsWith("x"),
        })
      : null;

  const finding = (
    rule: string,
    line: number | null,
    fix: string,
  ): HarnessFinding => ({
    severity: "error",
    rule,
    path: options.path,
    line,
    fix,
  });

  return options.conventions.flatMap(
    (convention): readonly HarnessFinding[] => {
      if (convention.kind === "file-length") {
        const lines = countLines(options.text);

        return isSource && lines > convention.maximumLines
          ? [
              finding(
                "file-length",
                convention.maximumLines + 1,
                `This file has ${lines} lines. Split it into a folder module so each file stays at or under ${convention.maximumLines} lines.`,
              ),
            ]
          : [];
      }

      if (convention.kind === "forbidden-text") {
        if (!isSource && !isProse) {
          return [];
        }

        return matchingLines({
          text: options.text,
          test: (line) => line.includes(convention.text),
        }).map((line) =>
          finding(
            `no-${convention.name}`,
            line,
            `Remove the ${convention.name} character and recast the sentence with a comma, parentheses, or a period.`,
          ),
        );
      }

      if (convention.kind === "no-suppressions") {
        return isSource
          ? suppressionLines({ text: options.text, comments }).map((line) =>
              finding(
                "no-suppressions",
                line,
                "Remove the suppression and fix the lint or type error it hides.",
              ),
            )
          : [];
      }

      return isTypescript && comments !== null
        ? comments.map((comment) =>
            finding(
              "no-comments",
              comment.line,
              "Delete the comment. Carry its meaning in a name, a type, or a test.",
            ),
          )
        : [];
    },
  );
}
