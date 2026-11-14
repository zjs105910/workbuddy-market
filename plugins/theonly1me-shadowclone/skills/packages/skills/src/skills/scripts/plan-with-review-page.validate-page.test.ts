import { expect, test } from "bun:test";
import { mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { seedSkillsDirectory } from "@shadowclone/core";

const skillDirectory = path.join(await seedSkillsDirectory(), "plan-with-review-page");
const validator = path.join(skillDirectory, "scripts/validate-page.mjs");
const template = path.join(skillDirectory, "assets/review-page.html");
const runtimes = [process.execPath, Bun.which("node")].flatMap((runtime) =>
  runtime ? [runtime] : [],
);
const emDash = String.fromCharCode(0x2014);

const filledPlan = {
  title: "Retire the testing skills",
  goal: "Builds that selected an old testing skill move to its replacement.",
  planPath: "/tmp/agent-artifacts/example/2026-01-01-retire-testing/plan.md",
  updated: "2026-01-01 09:00",
  steps: [
    { status: "done", text: "Read the build code.", note: "" },
    { status: "skipped", text: "Measure the wizard.", note: "The wizard is out of scope." },
  ],
  decisions: [{ question: "Edited copies?", answer: "Keep and list them.", source: "user" }],
  open: [],
  diagram: "flowchart LR\n  Build --> Sync",
};

async function page(options: {
  readonly plan?: unknown;
  readonly change?: (html: string) => string;
}): Promise<string> {
  const html = await Bun.file(template).text();
  const withPlan =
    options.plan === undefined
      ? html
      : html.replace(
          /(<script type="application\/json" id="plan">)[\s\S]*?(<\/script>)/,
          (_, open, close) => `${open}\n${JSON.stringify(options.plan, null, 2)}\n${close}`,
        );
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-page-")));
  const filePath = path.join(directory, "index.html");

  await Bun.write(filePath, options.change ? options.change(withPlan) : withPlan);

  return filePath;
}

function validate(options: { readonly runtime: string; readonly files: readonly string[] }) {
  const result = Bun.spawnSync([options.runtime, validator, ...options.files], {
    stdout: "pipe",
    stderr: "pipe",
  });

  return {
    exitCode: result.exitCode,
    lines: result.stdout.toString().trim().split("\n"),
    error: result.stderr.toString().trim(),
  };
}

for (const runtime of runtimes) {
  const name = path.basename(runtime);

  test(`${name}: the template fails until each template value is replaced`, async () => {
    const result = validate({ runtime, files: [await page({})] });

    expect(result.exitCode).toBe(1);
    expect(result.lines.at(-1)).toBe("validate-page: 12 errors in 1 file");
    expect(
      result.lines.some((line) => line.endsWith("error title still has template text, replace it")),
    ).toBeTrue();
  });

  test(`${name}: a filled page passes`, async () => {
    const result = validate({ runtime, files: [await page({ plan: filledPlan })] });

    expect(result).toEqual({
      exitCode: 0,
      lines: ["validate-page: 0 errors in 1 file"],
      error: "",
    });
  });

  test(`${name}: a bad status, a skip without a reason, and a dash are errors`, async () => {
    const filePath = await page({
      plan: {
        ...filledPlan,
        goal: `Move builds ${emDash} and keep edits.`,
        steps: [
          { status: "maybe", text: "Read the code.", note: "" },
          { status: "skipped", text: "Measure the wizard.", note: "" },
        ],
      },
    });
    const result = validate({ runtime, files: [filePath] });

    expect(result.exitCode).toBe(1);
    expect(result.lines).toEqual([
      `${filePath}: error steps[0].status must be one of todo, doing, done, blocked, skipped`,
      `${filePath}: error steps[1] is skipped, so its note must give the reason`,
      `${filePath}: error goal has an em or en dash, use a comma, a period, or parentheses`,
      "validate-page: 3 errors in 1 file",
    ]);
  });

  test(`${name}: another network script or a missing integrity hash fails`, async () => {
    const filePath = await page({
      plan: filledPlan,
      change: (html) =>
        html
          .replace("</body>", '<script src="https://example.com/tracker.js"></script>\n</body>')
          .replace(/sha384-[A-Za-z0-9+/=]+/, "sha384-removed"),
    });
    const result = validate({ runtime, files: [filePath] });

    expect(result.exitCode).toBe(1);
    expect(result.lines).toEqual([
      `${filePath}: error https://example.com/tracker.js loads from the network, keep the page self-contained`,
      `${filePath}: error the Mermaid script must keep its pinned integrity hash`,
      "validate-page: 2 errors in 1 file",
    ]);
  });

  test(`${name}: no file or a missing file stops with exit code 2`, async () => {
    const missing = path.join(os.tmpdir(), "shadowclone-page-missing.html");

    expect(validate({ runtime, files: [] })).toEqual({
      exitCode: 2,
      lines: [""],
      error: "Usage: validate-page.mjs <page.html>...",
    });
    expect(validate({ runtime, files: [missing] })).toEqual({
      exitCode: 2,
      lines: [""],
      error: `${missing}: cannot read the file (ENOENT)`,
    });
  });
}
