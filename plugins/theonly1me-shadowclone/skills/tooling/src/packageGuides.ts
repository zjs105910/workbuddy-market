import path from "node:path";
import { findFactsBlock, renderFacts, replaceFacts } from "./packageGuides/facts";
import { readWorkspaces, type Workspace } from "./packageGuides/workspaces";

export type GuideProblem = {
  readonly file: string;
  readonly message: string;
};

export type GuideReport = {
  readonly workspaceCount: number;
  readonly updatedFiles: readonly string[];
  readonly problems: readonly GuideProblem[];
};

type WorkspaceOutcome = {
  readonly updatedFiles: readonly string[];
  readonly problems: readonly GuideProblem[];
};

const claudeImport = "@AGENTS.md\n";

async function readText(file: string): Promise<string | null> {
  const source = Bun.file(file);

  return (await source.exists()) ? source.text() : null;
}

async function checkWorkspace(options: {
  readonly rootDirectory: string;
  readonly workspace: Workspace;
  readonly write: boolean;
}): Promise<WorkspaceOutcome> {
  const guideFile = path.join(options.workspace.directory, "AGENTS.md");
  const claudeFile = path.join(options.workspace.directory, "CLAUDE.md");
  const problems: GuideProblem[] = [];
  const guide = await readText(path.join(options.rootDirectory, guideFile));

  if ((await readText(path.join(options.rootDirectory, claudeFile))) !== claudeImport) {
    problems.push({
      file: claudeFile,
      message: `must contain exactly ${JSON.stringify(claudeImport)}`,
    });
  }

  if (guide === null) {
    return {
      updatedFiles: [],
      problems: [...problems, { file: guideFile, message: "is missing" }],
    };
  }

  if (findFactsBlock(guide).kind === "missing") {
    return {
      updatedFiles: [],
      problems: [...problems, { file: guideFile, message: "needs one package-facts block" }],
    };
  }

  const next = replaceFacts({ text: guide, facts: renderFacts(options.workspace) });

  if (next === guide) {
    return { updatedFiles: [], problems };
  }

  if (options.write && next !== null) {
    await Bun.write(path.join(options.rootDirectory, guideFile), next);

    return { updatedFiles: [guideFile], problems };
  }

  return {
    updatedFiles: [],
    problems: [
      ...problems,
      { file: guideFile, message: "has a package-facts block that is out of date" },
    ],
  };
}

export async function checkPackageGuides(options: {
  readonly rootDirectory: string;
  readonly write: boolean;
}): Promise<GuideReport> {
  const workspaces = await readWorkspaces(options);
  const updatedFiles: string[] = [];
  const problems: GuideProblem[] = [];

  for (const workspace of workspaces) {
    const outcome = await checkWorkspace({ ...options, workspace });

    updatedFiles.push(...outcome.updatedFiles);
    problems.push(...outcome.problems);
  }

  return { workspaceCount: workspaces.length, updatedFiles, problems };
}

if (import.meta.main) {
  const report = await checkPackageGuides({
    rootDirectory: process.cwd(),
    write: process.argv.includes("--write"),
  });

  for (const file of report.updatedFiles) {
    console.log(`${file}: updated the package-facts block`);
  }

  for (const problem of report.problems) {
    console.error(`${problem.file}: ${problem.message}`);
  }

  console.log(
    `guides: checked ${report.workspaceCount} workspaces, updated ${report.updatedFiles.length}, found ${report.problems.length} problems`,
  );

  if (report.problems.length > 0) {
    process.exitCode = 1;
  }
}
