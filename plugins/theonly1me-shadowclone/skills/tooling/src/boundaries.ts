import path from "node:path";
import {
  declaredGraph,
  findCycle,
  findViolations,
  observedGraph,
  type BoundaryViolation,
} from "./boundaries/check";
import { readImports, type ImportEdge } from "./boundaries/imports";
import { manifestViolations, readManifests } from "./boundaries/manifests";

export type BoundaryReport = {
  readonly fileCount: number;
  readonly violations: readonly BoundaryViolation[];
  readonly declaredCycle: readonly string[] | null;
  readonly observedCycle: readonly string[] | null;
};

const scannedPatterns = ["packages/*/src/**/*.ts", "evals/**/*.ts", "tooling/src/**/*.ts"] as const;

async function listScannedFiles(rootDirectory: string): Promise<readonly string[]> {
  const files: string[] = [];

  for (const pattern of scannedPatterns) {
    for await (const file of new Bun.Glob(pattern).scan({ cwd: rootDirectory })) {
      if (!file.split("/").includes("node_modules")) {
        files.push(file);
      }
    }
  }

  return files;
}

export async function checkBoundaries(options: { rootDirectory: string }): Promise<BoundaryReport> {
  const edges: ImportEdge[] = [];
  const files = await listScannedFiles(options.rootDirectory);
  const manifests = await readManifests(options.rootDirectory);

  for (const file of files) {
    const text = await Bun.file(path.join(options.rootDirectory, file)).text();

    edges.push(...readImports({ file, text }));
  }

  return {
    fileCount: files.length,
    violations: [...findViolations({ edges, manifests }), ...manifestViolations({ manifests })],
    declaredCycle: findCycle(declaredGraph()),
    observedCycle: findCycle(observedGraph({ edges })),
  };
}

if (import.meta.main) {
  const report = await checkBoundaries({ rootDirectory: process.cwd() });
  const ordered = [...report.violations].sort(
    (left, right) => left.file.localeCompare(right.file) || left.line - right.line,
  );

  for (const violation of ordered) {
    console.error(`${violation.file}:${violation.line}: ${violation.message}`);
  }

  for (const cycle of [report.declaredCycle, report.observedCycle]) {
    if (cycle) {
      console.error(`package cycle: ${cycle.join(" -> ")}`);
    }
  }

  const failed =
    ordered.length > 0 || report.declaredCycle !== null || report.observedCycle !== null;

  console.log(`boundaries: ${ordered.length} violations in ${report.fileCount} files`);

  if (failed) {
    process.exit(1);
  }
}
