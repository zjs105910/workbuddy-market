import path from "node:path";

export type SteFinding = {
  readonly file: string;
  readonly line: number;
  readonly level: "error" | "warning";
  readonly rule: string;
  readonly message: string;
};

const checkerPath = path.resolve(
  import.meta.dir,
  "../../../skills/write-plain-english/scripts/check-ste.mjs",
);
const findingPattern = /^(.+?):(\d+): (error|warning) (\S+) (.*)$/;
const filesPerRun = 100;

function parseFinding(line: string): SteFinding | null {
  const match = findingPattern.exec(line);
  const [, file, lineNumber, level, rule, message] = match ?? [];

  if (file === undefined || lineNumber === undefined || rule === undefined) {
    return null;
  }

  if (message === undefined || (level !== "error" && level !== "warning")) {
    return null;
  }

  return { file, line: Number(lineNumber), level, rule, message };
}

function runChecker(options: {
  readonly rootDirectory: string;
  readonly files: readonly string[];
}): readonly SteFinding[] {
  const result = Bun.spawnSync([process.execPath, checkerPath, ...options.files], {
    cwd: options.rootDirectory,
    stdout: "pipe",
    stderr: "pipe",
  });

  if (result.exitCode !== 0 && result.exitCode !== 1) {
    throw new Error(`The STE checker did not run: ${result.stderr.toString().trim()}`);
  }

  return result.stdout
    .toString()
    .split("\n")
    .flatMap((line) => {
      const finding = parseFinding(line);

      return finding === null ? [] : [finding];
    });
}

export function steFindings(options: {
  readonly rootDirectory: string;
  readonly files: readonly string[];
}): readonly SteFinding[] {
  const findings: SteFinding[] = [];

  for (let start = 0; start < options.files.length; start += filesPerRun) {
    findings.push(
      ...runChecker({
        rootDirectory: options.rootDirectory,
        files: options.files.slice(start, start + filesPerRun),
      }),
    );
  }

  return findings;
}
