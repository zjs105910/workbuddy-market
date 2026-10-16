import ts from "typescript";

const maximumLineCount = 300;
const dashRules = [
  {
    character: "\u2014",
    rule: "no-em-dash",
    message: "em dash, recast with plain punctuation",
  },
  {
    character: "\u2013",
    rule: "no-en-dash",
    message: "en dash, write \"to\" for a range or recast the sentence",
  },
] as const;
const codeSuffix = ".ts";
const proseSuffixes = [
  ".md",
  ".ts",
  ".mjs",
  ".html",
  ".yml",
  ".yaml",
  ".json",
] as const;

const skippedDirectories = [
  ".git",
  "node_modules",
  "dist",
  "out",
  "coverage",
  ".turbo",
] as const;

export type Violation = {
  readonly file: string;
  readonly line: number;
  readonly rule: string;
  readonly message: string;
};

export type ConventionReport = {
  readonly checkedFileCount: number;
  readonly violations: readonly Violation[];
};

async function listFiles(options: {
  rootDirectory: string;
}): Promise<readonly string[]> {
  const glob = new Bun.Glob("**/*");
  const files: string[] = [];

  for await (const file of glob.scan({
    cwd: options.rootDirectory,
    onlyFiles: true,
    dot: true,
  })) {
    const segments = file.split("/");
    const skipped = skippedDirectories.some((directory) =>
      segments.includes(directory),
    );

    if (!skipped) {
      files.push(file);
    }
  }

  return files.sort();
}

function countLines(text: string): number {
  if (text === "") {
    return 0;
  }

  const lineCount = text.split("\n").length;

  return text.endsWith("\n") ? lineCount - 1 : lineCount;
}

function lineOfPosition(options: { text: string; position: number }): number {
  return options.text.slice(0, options.position).split("\n").length;
}

function commentPositions(text: string): readonly number[] {
  const source = ts.createSourceFile(
    "source.ts",
    text,
    ts.ScriptTarget.Latest,
    true,
  );
  const positions = new Set<number>();

  function visit(node: ts.Node): void {
    const ranges = [
      ...(ts.getLeadingCommentRanges(text, node.pos) ?? []),
      ...(ts.getTrailingCommentRanges(text, node.end) ?? []),
    ];

    for (const range of ranges) {
      positions.add(range.pos);
    }

    for (const child of node.getChildren(source)) {
      visit(child);
    }
  }

  visit(source);

  return [...positions].sort((left, right) => left - right);
}

function codeViolations(options: {
  file: string;
  text: string;
}): readonly Violation[] {
  const lineCount = countLines(options.text);

  const lengthViolations =
    lineCount > maximumLineCount
      ? [
          {
            file: options.file,
            line: maximumLineCount + 1,
            rule: "file-length",
            message: `${lineCount} lines, over the ${maximumLineCount} line limit`,
          },
        ]
      : [];

  return [
    ...lengthViolations,
    ...commentPositions(options.text).map((position) => ({
      file: options.file,
      line: lineOfPosition({ text: options.text, position }),
      rule: "no-comments",
      message: "comment, the project writes none",
    })),
  ];
}

function proseViolations(options: {
  file: string;
  text: string;
}): readonly Violation[] {
  const violations: Violation[] = [];

  for (const [lineIndex, line] of options.text.split("\n").entries()) {
    for (const dash of dashRules) {
      if (line.includes(dash.character)) {
        violations.push({
          file: options.file,
          line: lineIndex + 1,
          rule: dash.rule,
          message: dash.message,
        });
      }
    }
  }

  return violations;
}

export async function findConventionViolations(options: {
  rootDirectory: string;
}): Promise<ConventionReport> {
  const files = await listFiles({ rootDirectory: options.rootDirectory });
  const violations: Violation[] = [];
  let checkedFileCount = 0;

  for (const file of files) {
    const isCode = file.endsWith(codeSuffix);
    const isProse = proseSuffixes.some((suffix) => file.endsWith(suffix));

    if (!isCode && !isProse) {
      continue;
    }

    const text = await Bun.file(`${options.rootDirectory}/${file}`).text();

    checkedFileCount += 1;

    if (isCode) {
      violations.push(...codeViolations({ file, text }));
    }

    if (isProse) {
      violations.push(...proseViolations({ file, text }));
    }
  }

  return { checkedFileCount, violations };
}

if (import.meta.main) {
  const report = await findConventionViolations({
    rootDirectory: process.cwd(),
  });

  for (const violation of report.violations) {
    console.log(
      `${violation.file}:${violation.line} ${violation.rule} ${violation.message}`,
    );
  }

  console.log(
    `conventions: checked ${report.checkedFileCount} files, found ${report.violations.length} violations`,
  );

  if (report.violations.length > 0) {
    process.exitCode = 1;
  }
}
