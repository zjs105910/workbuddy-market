import { expect, test } from "bun:test";
import { mkdtemp, realpath } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { seedSkillsDirectory } from "@shadowclone/core";

const checker = path.join(
  await seedSkillsDirectory(),
  "write-plain-english/scripts/check-ste.mjs",
);
const runtimes = [process.execPath, Bun.which("node")].flatMap((runtime) =>
  runtime ? [runtime] : [],
);

async function textFile(text: string): Promise<string> {
  const directory = await realpath(await mkdtemp(path.join(os.tmpdir(), "shadowclone-ste-")));
  const filePath = path.join(directory, "text.md");

  await Bun.write(filePath, text);

  return filePath;
}

function check(options: { readonly runtime: string; readonly files: readonly string[] }) {
  const result = Bun.spawnSync([options.runtime, checker, ...options.files], {
    stdout: "pipe",
    stderr: "pipe",
  });

  return {
    exitCode: result.exitCode,
    lines: result.stdout.toString().trim().split("\n"),
    error: result.stderr.toString().trim(),
  };
}

const longSentence = `${Array.from({ length: 30 }, (_, index) => `word${index}`).join(" ")}.`;

for (const runtime of runtimes) {
  const name = path.basename(runtime);

  test(`${name}: a dash and a long sentence are errors, and the exit code is 1`, async () => {
    const filePath = await textFile(`Use a comma \u2014 not a dash.\n\n${longSentence}\n`);
    const result = check({ runtime, files: [filePath] });

    expect(result.exitCode).toBe(1);
    expect(result.lines).toEqual([
      `${filePath}:1: error dash replace the em or en dash with a comma, a period, parentheses, or the word to`,
      `${filePath}:3: error long-sentence 30 words, split it to 25 or fewer: "${longSentence.slice(0, 60)}"`,
      "check-ste: 2 errors, 0 warnings in 1 file",
    ]);
  });

  test(`${name}: code, quoted examples, and frontmatter keys are not checked`, async () => {
    const filePath = await textFile(
      [
        "---",
        "name: sample-skill",
        "description: Use when the text is short.",
        "---",
        "Run `node check.mjs --flag=a\u2013b` on the file.",
        'Use a single verb, not "kick off".',
        "```",
        `${longSentence} \u2014`,
        "```",
        "",
      ].join("\n"),
    );
    const result = check({ runtime, files: [filePath] });

    expect(result.exitCode).toBe(0);
    expect(result.lines).toEqual(["check-ste: 0 errors, 0 warnings in 1 file"]);
  });

  test(`${name}: a sentence that starts with inline code is its own sentence`, async () => {
    const filePath = await textFile(
      "The sync command updates every copy of each bundled skill on the machine. `sync` prints one line for each change that it makes to a copy.\n",
    );

    expect(check({ runtime, files: [filePath] }).lines).toEqual([
      "check-ste: 0 errors, 0 warnings in 1 file",
    ]);
  });

  test(`${name}: passive voice, phrasal verbs, and vague words are warnings only`, async () => {
    const filePath = await textFile(
      "The file was deleted by the script. We set up the tool. This fix is robust.\n",
    );
    const result = check({ runtime, files: [filePath] });

    expect(result.exitCode).toBe(0);
    expect(result.lines.map((line) => line.split(" ").slice(1, 3).join(" "))).toEqual([
      "warning passive",
      "warning phrasal-verb",
      "warning vague-word",
      "0 errors,",
    ]);
  });

  test(`${name}: no file or a missing file stops with exit code 2`, async () => {
    const missing = path.join(os.tmpdir(), "shadowclone-ste-missing.md");

    expect(check({ runtime, files: [] })).toEqual({
      exitCode: 2,
      lines: [""],
      error: "Usage: check-ste.mjs <file>...",
    });
    expect(check({ runtime, files: [missing] })).toEqual({
      exitCode: 2,
      lines: [""],
      error: `${missing}: cannot read the file (ENOENT)`,
    });
  });
}
