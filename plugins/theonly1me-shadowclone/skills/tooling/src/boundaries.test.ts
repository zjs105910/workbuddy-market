import { expect, test } from "bun:test";
import { checkBoundaries } from "./boundaries";
import {
  declaredGraph,
  findCycle,
  findViolations,
  observedGraph,
  packageOfFile,
} from "./boundaries/check";
import { readImports } from "./boundaries/imports";
import { edgesOf, manifestOf, treeWith } from "./boundaries/testing";

test("reads value, type, dynamic, re-export, and side-effect imports with their line numbers", () => {
  const edges = readImports({
    file: "packages/cli/src/a.ts",
    text: [
      'import { one } from "../config";',
      'import type { Two } from "../paths";',
      "",
      'export { three } from "../io/files";',
      'const lazy = await import("../mcp");',
      'import "../storage";',
      'import { z } from "zod";',
    ].join("\n"),
  });

  expect(edges.map((edge) => [edge.line, edge.specifier])).toEqual([
    [1, "../config"],
    [2, "../paths"],
    [4, "../io/files"],
    [5, "../mcp"],
    [6, "../storage"],
    [7, "zod"],
  ]);
});

test("a file belongs to the package that owns its top-level module", () => {
  expect(packageOfFile("packages/core/src/paths.test.ts")).toBe("core");
  expect(packageOfFile("packages/core/src/product.json")).toBe("core");
  expect(packageOfFile("packages/skills/src/skillMaintenance/state.ts")).toBe("skills");
  expect(packageOfFile("packages/environment/src/integrations/hooks.test.ts")).toBe("environment");
  expect(packageOfFile("packages/learning/src/distill/reconcile/run.ts")).toBe("learning");
  expect(packageOfFile("packages/cli/src/harnessCommands/init.test.ts")).toBe("cli");
  expect(packageOfFile("packages/unlisted/src/a.ts")).toBeNull();
  expect(packageOfFile("evals/shared/a.ts")).toBeNull();
});

test("an import inside a package and an import of an allowed package pass", () => {
  const edges = edgesOf({
    "packages/cli/src/a.ts":
      'import { x } from "@shadowclone/environment";\nimport { y } from "./b";',
    "packages/learning/src/a.ts": 'import type { z } from "@shadowclone/environment";',
    "packages/environment/src/integrations/a.test.ts": 'import { z } from "../environment/store";',
  });
  const manifests = new Map([
    manifestOf({ key: "environment" }),
    manifestOf({ key: "cli", workspaceDependencies: ["@shadowclone/environment"] }),
    manifestOf({ key: "learning", workspaceDependencies: ["@shadowclone/environment"] }),
  ]);

  expect(findViolations({ edges, manifests })).toEqual([]);
});

test("a value import, a type import, and a test import that break the table are reported with their position", () => {
  const edges = edgesOf({
    "packages/environment/src/a.ts": '\nimport { x } from "@shadowclone/cli";',
    "packages/builds/src/b.ts": 'import type { Y } from "@shadowclone/learning";',
    "packages/harness/src/c.test.ts": 'const a = 1;\nimport { z } from "@shadowclone/web";',
  });
  const manifests = new Map([
    manifestOf({ key: "cli" }),
    manifestOf({ key: "learning" }),
    manifestOf({ key: "web" }),
    manifestOf({ key: "environment", workspaceDependencies: ["@shadowclone/cli"] }),
    manifestOf({ key: "builds", workspaceDependencies: ["@shadowclone/learning"] }),
    manifestOf({ key: "harness", workspaceDependencies: ["@shadowclone/web"] }),
  ]);

  expect(findViolations({ edges, manifests })).toEqual([
    {
      file: "packages/environment/src/a.ts",
      line: 2,
      message: '"@shadowclone/cli" makes environment depend on cli',
    },
    {
      file: "packages/builds/src/b.ts",
      line: 1,
      message: '"@shadowclone/learning" makes builds depend on learning',
    },
    {
      file: "packages/harness/src/c.test.ts",
      line: 2,
      message: '"@shadowclone/web" makes harness depend on web',
    },
  ]);
});

test("an import that leaves its package folder or comes from a file outside every package is reported", () => {
  const edges = edgesOf({
    "packages/mcp/src/a.ts": 'import data from "../../../package.json";',
    "packages/mcp/src/b.ts": 'import { x } from "../../unlisted/src/x";',
    "scripts/c.ts": 'import { x } from "./config";',
  });

  expect(findViolations({ edges }).map((violation) => violation.message)).toEqual([
    '"../../../package.json" leaves its package',
    '"../../unlisted/src/x" leaves its package',
    "file belongs to no package",
  ]);
});

test("a cycle between packages is found, and an acyclic graph has none", () => {
  const cycle = findCycle(
    new Map([
      ["a", new Set(["b"])],
      ["b", new Set(["c"])],
      ["c", new Set(["a"])],
    ]),
  );

  expect(cycle).toEqual(["a", "b", "c", "a"]);
  expect(
    findCycle(
      new Map([
        ["a", new Set(["b"])],
        ["b", new Set()],
      ]),
    ),
  ).toBeNull();
});

test("the declared dependency table and an import graph that follows it have no cycle", () => {
  const edges = edgesOf({
    "packages/cli/src/a.ts": 'import { x } from "@shadowclone/mcp";',
    "packages/mcp/src/a.ts": 'import { x } from "@shadowclone/environment";',
    "packages/environment/src/a.ts": 'import { x } from "@shadowclone/core";',
  });

  expect(findCycle(declaredGraph())).toBeNull();
  expect(findCycle(observedGraph({ edges }))).toBeNull();
});

test("the observed graph reports a cycle that the import edges form", () => {
  const edges = edgesOf({
    "packages/environment/src/a.ts": 'import { x } from "@shadowclone/builds";',
    "packages/builds/src/a.ts": 'import { x } from "@shadowclone/environment";',
  });

  expect(findCycle(observedGraph({ edges }))).toEqual(["environment", "builds", "environment"]);
});

test("the checker reads every source file under src and counts the files it read", async () => {
  const rootDirectory = await treeWith({
    "packages/environment/src/a.ts": 'import { x } from "../../cli/src/doctor";\n',
    "packages/cli/src/doctor.ts": "export const x = 1;\n",
    "docs/ignored.ts": 'import { x } from "../packages/cli/src/doctor";\n',
  });

  const report = await checkBoundaries({ rootDirectory });

  expect(report.fileCount).toBe(2);
  expect(report.violations).toEqual([
    {
      file: "packages/environment/src/a.ts",
      line: 1,
      message: '"../../cli/src/doctor" leaves its package',
    },
  ]);
  expect(report.observedCycle).toBeNull();
});
