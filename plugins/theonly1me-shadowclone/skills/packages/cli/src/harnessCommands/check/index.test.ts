import { expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import path from "node:path";
import { renderCheckReport, runHarnessCheck } from "@shadowclone/harness";
import { checkedRepository, git } from "./testRepository";

const emDash = String.fromCharCode(0x2014);

test("harness check reports each convention with a fix in changed files only", async () => {
  const setup = await checkedRepository();

  await Bun.write(
    path.join(setup.root, "src/long.ts"),
    `${Array.from({ length: 201 }, (_, index) => `export const value${index} = ${index};`).join("\n")}\n`,
  );
  await Bun.write(
    path.join(setup.root, "src/commented.ts"),
    "export const answer = 42;\n// explains the answer\n",
  );
  await Bun.write(
    path.join(setup.root, "src/suppressed.ts"),
    'const text = "// @ts-ignore is only text";\n/* @ts-ignore */\nexport const value: number = text.length;\n',
  );
  await Bun.write(
    path.join(setup.root, "docs/notes.md"),
    `A pause ${emDash} then more.\n`,
  );

  const report = await runHarnessCheck({ root: setup.root, changed: true });
  const rules = report.findings
    .filter((finding) => finding.severity === "error")
    .map((finding) => `${finding.rule} ${finding.path}:${finding.line}`);

  expect(rules.sort()).toEqual([
    "file-length src/long.ts:201",
    "no-comments src/commented.ts:2",
    "no-comments src/suppressed.ts:2",
    "no-em-dash docs/notes.md:1",
    "no-suppressions src/suppressed.ts:2",
  ]);
  expect(
    report.findings.find((finding) => finding.rule === "file-length")?.fix,
  ).toContain("Split it into a folder module");
  expect(report.checkedFiles).toBe(4);
});

test("--changed checks only uncommitted files, so older violations do not block new work", async () => {
  const setup = await checkedRepository();

  await Bun.write(
    path.join(setup.root, "src/legacy.ts"),
    "export const legacy = 1;\n// older note\n",
  );
  git({ root: setup.root, arguments: ["add", "-A"] });
  git({ root: setup.root, arguments: ["commit", "-q", "-m", "legacy"] });
  await Bun.write(
    path.join(setup.root, "src/clean.ts"),
    "export const clean = true;\n",
  );

  const changed = await runHarnessCheck({ root: setup.root, changed: true });

  expect(
    changed.findings.filter((finding) => finding.severity === "error"),
  ).toEqual([]);
  expect(renderCheckReport({ report: changed, format: "human" }).exitCode).toBe(
    0,
  );

  const full = await runHarnessCheck({ root: setup.root, changed: false });

  expect(
    full.findings.map((finding) => `${finding.rule} ${finding.path}`),
  ).toContain("no-comments src/legacy.ts");
});

test("health checks catch a lost import, an edited section, and a missing gate script", async () => {
  const setup = await checkedRepository();

  await Bun.write(
    path.join(setup.root, "CLAUDE.md"),
    "# Claude instructions\n",
  );

  const agents = await Bun.file(path.join(setup.root, "AGENTS.md")).text();

  await Bun.write(
    path.join(setup.root, "AGENTS.md"),
    agents.replace("Run it before presenting any change.", "Run it sometimes."),
  );

  const packageJson = JSON.parse(
    await Bun.file(path.join(setup.root, "package.json")).text(),
  );

  await Bun.write(
    path.join(setup.root, "package.json"),
    JSON.stringify({ ...packageJson, scripts: { test: "bun test" } }),
  );

  const findings = (
    await runHarnessCheck({ root: setup.root, changed: false })
  ).findings.map((finding) => `${finding.severity} ${finding.rule}`);

  expect(findings).toEqual(
    expect.arrayContaining([
      "warning claude-import",
      "warning agents-edited",
      "error gate-script",
      "warning gate-ci",
    ]),
  );
});

test("a missing harness is reported with the init command, and a broken manifest stops the check", async () => {
  const setup = await checkedRepository();

  await rm(path.join(setup.root, ".shadowclone/harness.json"));

  const missing = await runHarnessCheck({ root: setup.root, changed: false });

  expect(missing.findings[0]?.fix).toContain("shadowclone init --repo");
  expect(
    missing.findings.map((finding) => `${finding.severity} ${finding.rule}`),
  ).toEqual(["error harness-missing"]);

  await Bun.write(path.join(setup.root, ".shadowclone/harness.json"), "");

  await expect(
    runHarnessCheck({ root: setup.root, changed: false }),
  ).rejects.toThrow("restore it from version control");
});
