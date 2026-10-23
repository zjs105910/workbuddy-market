import { expect, test } from "bun:test";
import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { findConventionViolations } from "./conventions";

async function treeWith(files: Record<string, string>): Promise<string> {
  const rootDirectory = await mkdtemp(
    path.join(os.tmpdir(), "shadowclone-conventions-"),
  );

  for (const [file, text] of Object.entries(files)) {
    await Bun.write(path.join(rootDirectory, file), text);
  }

  return rootDirectory;
}

test("passes a tree that follows the conventions", async () => {
  const rootDirectory = await treeWith({
    "src/paths.ts": 'export const home = "~";\n',
    "README.md": "# title\n\nPlain prose, no em dash.\n",
  });

  const report = await findConventionViolations({ rootDirectory });

  expect(report.violations).toEqual([]);
  expect(report.checkedFileCount).toBe(2);
});

test("flags a source file over the line limit", async () => {
  const rootDirectory = await treeWith({
    "src/long.ts": `${Array.from({ length: 301 }, () => "export {};").join("\n")}\n`,
  });

  const report = await findConventionViolations({ rootDirectory });

  expect(report.violations).toEqual([
    {
      file: "src/long.ts",
      line: 301,
      rule: "file-length",
      message: "301 lines, over the 300 line limit",
    },
  ]);
});

test("flags a comment and leaves a url inside a string alone", async () => {
  const rootDirectory = await treeWith({
    "src/commented.ts": [
      'export const docs = "https://bun.sh/docs";',
      "export const pattern = /a\\/b/;",
      "export const count = 1; // why",
      "/* block */",
      "",
    ].join("\n"),
  });

  const report = await findConventionViolations({ rootDirectory });

  expect(report.violations.map((violation) => violation.line)).toEqual([3, 4]);
  expect(
    report.violations.every((violation) => violation.rule === "no-comments"),
  ).toBeTrue();
});

test("flags a suppression, which only exists inside a comment", async () => {
  const rootDirectory = await treeWith({
    "src/suppressed.ts": [
      "// biome-ignore lint/suspicious/noExplicitAny: shortcut",
      "export const value = 1;",
      "",
    ].join("\n"),
  });

  const report = await findConventionViolations({ rootDirectory });

  expect(report.violations.map((violation) => violation.rule)).toEqual([
    "no-comments",
  ]);
});

test("distinguishes comments from nested template text", async () => {
  const rootDirectory = await treeWith({
    "src/templates.ts": [
      `const token = \`\${crypto.randomUUID()}\${crypto.randomUUID()}\`;`,
      `const origin = \`http://127.0.0.1:\${port}\`;`,
      `const nested = \`\${\`https://\${host}\`}/path\`;`,
      `const value = \`\${/* actual comment */ token}\`;`,
      `const tail = \`\${token}\`; // another comment`,
      "",
    ].join("\n"),
  });

  const report = await findConventionViolations({ rootDirectory });

  expect(report.violations.map((violation) => violation.line)).toEqual([4, 5]);
});

test("flags an em dash in prose and in source", async () => {
  const rootDirectory = await treeWith({
    "docs/design/002.md": "A sentence \u2014 with an em dash.\n",
    "src/label.ts": 'export const label = "one \u2014 two";\n',
  });

  const report = await findConventionViolations({ rootDirectory });

  expect(report.violations.map((violation) => violation.file)).toEqual([
    "docs/design/002.md",
    "src/label.ts",
  ]);
  expect(
    report.violations.every((violation) => violation.rule === "no-em-dash"),
  ).toBeTrue();
});

test("flags an en dash in a document, a script, and a page", async () => {
  const rootDirectory = await treeWith({
    "docs/guide.md": "Steps 2\u20135 run in order.\n",
    "skills/sample/scripts/check.mjs": 'export const range = "1\u20139";\n',
    "skills/sample/assets/page.html": "<p>Mon\u2013Fri</p>\n",
  });

  const report = await findConventionViolations({ rootDirectory });

  expect(report.checkedFileCount).toBe(3);
  expect(
    report.violations.map((violation) => `${violation.file}:${violation.line} ${violation.rule}`),
  ).toEqual([
    "docs/guide.md:1 no-en-dash",
    "skills/sample/assets/page.html:1 no-en-dash",
    "skills/sample/scripts/check.mjs:1 no-en-dash",
  ]);
});

test("reads no file inside a skipped directory", async () => {
  const rootDirectory = await treeWith({
    "node_modules/library/index.ts": "// vendored comment\n",
    "dist/bundle.ts": "// generated comment\n",
    "src/paths.ts": "export {};\n",
  });

  const report = await findConventionViolations({ rootDirectory });

  expect(report.violations).toEqual([]);
  expect(report.checkedFileCount).toBe(1);
});
