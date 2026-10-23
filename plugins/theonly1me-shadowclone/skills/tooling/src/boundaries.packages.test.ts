import { expect, test } from "bun:test";
import { checkBoundaries } from "./boundaries";
import { findCycle, findViolations, observedGraph } from "./boundaries/check";
import type { ManifestIndex } from "./boundaries/manifests";
import { edgesOf, manifestOf, treeWith } from "./boundaries/testing";

const manifests: ManifestIndex = new Map([
  manifestOf({ key: "core", exportedSubpaths: [".", "./testing"] }),
  manifestOf({ key: "redact", workspaceDependencies: ["@shadowclone/core"] }),
  manifestOf({ key: "agents" }),
  manifestOf({ key: "web", workspaceDependencies: ["@shadowclone/builds"] }),
  manifestOf({ key: "builds", exportedSubpaths: [".", "./browser"] }),
  manifestOf({ key: "evals", workspaceDependencies: ["@shadowclone/core"] }),
]);

function messagesFor(files: Record<string, string>) {
  return findViolations({ edges: edgesOf(files), manifests }).map((violation) => violation.message);
}

test("a declared, exported, allowed package import passes in a package and in evals", () => {
  expect(
    messagesFor({
      "packages/redact/src/a.ts": 'import { x } from "@shadowclone/core";',
      "packages/redact/src/b.test.ts": 'import { y } from "@shadowclone/core/testing";',
      "evals/fixed/a.ts": 'import { x } from "@shadowclone/core";',
    }),
  ).toEqual([]);
});

test("a subpath that the target does not export is reported", () => {
  expect(
    messagesFor({ "evals/fixed/a.ts": 'import { x } from "@shadowclone/core/internal/rules";' }),
  ).toEqual([
    '"@shadowclone/core/internal/rules" is not listed in the exports of @shadowclone/core',
  ]);
});

test("a package that the importing package.json does not declare is reported", () => {
  expect(
    messagesFor({ "packages/redact/src/a.ts": 'import { x } from "@shadowclone/agents";' }),
  ).toEqual([
    "@shadowclone/agents is not declared in the package.json that owns this file",
    '"@shadowclone/agents" makes redact depend on agents',
  ]);
  expect(messagesFor({ "evals/fixed/a.ts": 'import { x } from "@shadowclone/redact";' })).toEqual([
    "@shadowclone/redact is not declared in the package.json that owns this file",
  ]);
});

test("a package that imports its own name, a missing package, or a higher package is reported", () => {
  expect(
    messagesFor({
      "packages/core/src/config/a.ts": 'import { x } from "@shadowclone/core";',
      "packages/core/src/config/b.ts": 'import { x } from "@shadowclone/missing";',
    }),
  ).toEqual([
    "@shadowclone/core is not declared in the package.json that owns this file",
    '"@shadowclone/core" makes core import its own package',
    '"@shadowclone/missing" is not a workspace package',
  ]);
});

test("a relative import that leaves its package folder is reported, and one that stays is not", () => {
  expect(
    messagesFor({
      "packages/redact/src/a.ts": 'import { x } from "../../core/src/paths";',
      "packages/redact/src/b.ts": 'import { y } from "../../../scripts/build";',
      "packages/redact/src/c.ts": 'import { z } from "./rules";',
    }),
  ).toEqual([
    '"../../core/src/paths" leaves its package',
    '"../../../scripts/build" leaves its package',
  ]);
});

test("a package and evals cannot reach into another package folder by a relative path", () => {
  expect(
    messagesFor({
      "packages/cli/src/a.ts": 'import { x } from "../../core/src/paths";',
      "evals/fixed/a.ts": 'import { y } from "../../packages/core/src/paths";',
      "evals/fixed/b.ts": 'import { z } from "../shared/helper";',
    }),
  ).toEqual([
    '"../../core/src/paths" leaves its package',
    '"../../packages/core/src/paths" leaves its package',
  ]);
});

test("the web client and the files that it loads import another package only through its browser subpath", () => {
  const violations = findViolations({
    edges: edgesOf({
      "packages/web/src/client/a.ts": [
        'import { x } from "@shadowclone/builds/browser";',
        'import { p } from "../protocol";',
        'import type { N } from "../typesOnly";',
      ].join("\n"),
      "packages/web/src/protocol.ts": 'import { z } from "@shadowclone/builds";',
      "packages/web/src/typesOnly.ts": 'import { y } from "@shadowclone/builds";',
      "packages/web/src/server.ts": 'import { y } from "@shadowclone/builds";',
    }),
    manifests,
  });

  expect(violations.map((violation) => [violation.file, violation.message])).toEqual([
    [
      "packages/web/src/protocol.ts",
      '"@shadowclone/builds" is not a ./browser subpath, and the web client must not load node code',
    ],
  ]);
});

test("the observed graph counts a package import by name and reports the cycle that it closes", () => {
  const edges = edgesOf({
    "packages/core/src/config/a.ts": 'import { x } from "@shadowclone/redact";',
    "packages/redact/src/a.ts": 'import { x } from "@shadowclone/core";',
  });

  expect(findCycle(observedGraph({ edges }))).toEqual(["core", "redact", "core"]);
});

test("the checker reports a package.json that breaks the rules", async () => {
  const rootDirectory = await treeWith({
    "package.json": JSON.stringify({
      name: "shadowclone",
      devDependencies: { "@shadowclone/nope": "workspace:*" },
    }),
    "packages/redact/package.json": JSON.stringify({
      name: "@shadowclone/redact",
      version: "1.0.0",
      dependencies: { "@shadowclone/agents": "workspace:*" },
    }),
    "packages/redact/src/a.ts": "export const a = 1;\n",
  });

  const report = await checkBoundaries({ rootDirectory });

  expect(report.fileCount).toBe(1);
  expect(report.violations.map((violation) => [violation.file, violation.message])).toEqual([
    ["package.json", "@shadowclone/nope is not a workspace package"],
    ["packages/redact/package.json", "a workspace package must be private"],
    ["packages/redact/package.json", "a workspace package has no version"],
    ["packages/redact/package.json", "agents is not a dependency that redact may declare"],
  ]);
});
