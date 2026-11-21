import { chmodSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { cases } from "./cases";
import { runCommand } from "./fakeGh/git";
import type { CaseDefinition } from "./scaffold/definition";

export const pluginName = "shadowclone-work-eval";
export const variantNames = ["baseline", "skill-only"] as const;
export type VariantName = (typeof variantNames)[number];

const evalDirectory = path.dirname(new URL(import.meta.url).pathname);
const repositoryRoot = path.resolve(evalDirectory, "..", "..");

export const defaultSkillFile = path.join(repositoryRoot, "skills", "shadowclone-work", "SKILL.md");

export function defaultOutputDirectory(): string {
  return path.join(os.homedir(), ".cache", "shadowclone-evals", "shadowclone-work", "build");
}

function writeExecutable(options: { readonly file: string; readonly text: string }): void {
  writeFileSync(options.file, options.text);
  chmodSync(options.file, 0o755);
}

const environmentHook = `#!/bin/sh
root="\${CLAUDE_PROJECT_DIR:-$PWD}"
if [ -n "$CLAUDE_ENV_FILE" ] && [ -x "$root/bin/gh" ]; then
  printf 'export PATH="%s/bin:$PATH"\\n' "$root" >> "$CLAUDE_ENV_FILE"
  if [ -d "$root/bin/git-core" ]; then
    printf 'export GIT_EXEC_PATH="%s/bin/git-core"\\n' "$root" >> "$CLAUDE_ENV_FILE"
  fi
fi
`;

function caseFiles(options: {
  readonly definition: CaseDefinition;
  readonly caseDirectory: string;
  readonly output: string;
  readonly withSkill: boolean;
}): void {
  const { definition, caseDirectory, output } = options;

  mkdirSync(path.join(caseDirectory, "graders"), { recursive: true });
  writeFileSync(
    path.join(caseDirectory, "prompt.md"),
    `---\ntags: [${[definition.split, ...definition.tags].join(", ")}]\nmax_turns: 100\ntimeout_seconds: 900\nallowed_tools: [Read, Glob, Grep, Skill, TodoWrite]\n---\n\n${definition.prompt}\n`,
  );
  writeFileSync(path.join(caseDirectory, "case.yaml"), `schema_version: "1.1"\nname: ${definition.id}\ncontext:\n  scaffold_script: scaffold.sh\n`);
  writeExecutable({
    file: path.join(caseDirectory, "scaffold.sh"),
    text: `#!/bin/bash\nset -euo pipefail\nexec "${process.execPath}" "${path.join(evalDirectory, "scaffold", "cli.ts")}" "${definition.id}" "$PWD" "${path.join(output, "bin", "gh")}"\n`,
  });
  if (options.withSkill) {
    writeFileSync(path.join(caseDirectory, "graders", "skill.md"), "---\ntype: tool_used\ntool: Skill\narm: with-only\n---\n\nThe shadowclone-work skill was invoked.\n");
  }
  writeFileSync(
    path.join(caseDirectory, "graders", "report.md"),
    "---\ntype: llm\n---\n\nThe final message is a short report. It passes only if all of these hold:\n1. It names the pull request number or numbers and states the state of the checks.\n2. For every review comment it fixed, it gives a commit SHA.\n3. For every review comment it did not fix, it gives a one-line reason.\n4. It does not claim that any pull request was merged.\n5. It does not claim a check passed when the same message says that check failed or was not run.\n",
  );
}

function buildVariant(options: { readonly output: string; readonly variant: VariantName; readonly skillText: string }): string {
  const root = path.join(options.output, "variants", options.variant);

  rmSync(path.join(root, "evals"), { recursive: true, force: true });
  rmSync(path.join(root, "skills"), { recursive: true, force: true });
  mkdirSync(path.join(root, ".claude-plugin"), { recursive: true });
  mkdirSync(path.join(root, "hooks"), { recursive: true });
  writeExecutable({ file: path.join(root, "hooks", "environment.sh"), text: environmentHook });
  writeFileSync(
    path.join(root, "hooks", "hooks.json"),
    `${JSON.stringify({ hooks: { SessionStart: [{ hooks: [{ type: "command", command: path.join(root, "hooks", "environment.sh") }] }] } }, null, 2)}\n`,
  );
  writeFileSync(
    path.join(root, ".claude-plugin", "plugin.json"),
    `${JSON.stringify({ name: pluginName, version: "0.0.0", description: `shadowclone-work evaluation variant ${options.variant}` }, null, 2)}\n`,
  );
  if (options.variant !== "baseline") {
    mkdirSync(path.join(root, "skills", "shadowclone-work"), { recursive: true });
    writeFileSync(path.join(root, "skills", "shadowclone-work", "SKILL.md"), options.skillText);
  }

  for (const definition of cases) {
    caseFiles({ definition, caseDirectory: path.join(root, "evals", definition.id), output: options.output, withSkill: options.variant !== "baseline" });
  }

  return root;
}

export function prepare(options: { readonly output: string; readonly skillFile: string }): readonly string[] {
  mkdirSync(path.join(options.output, "bin"), { recursive: true });

  const compiled = runCommand({
    command: [process.execPath, "build", "--compile", path.join(evalDirectory, "fakeGh", "main.ts"), "--outfile", path.join(options.output, "bin", "gh")],
    cwd: repositoryRoot,
  });

  if (compiled.exitCode !== 0) {
    throw new Error(`Could not compile the fake gh: ${compiled.stderr}`);
  }

  const skillText = readFileSync(options.skillFile, "utf8");

  return variantNames.map((variant) => buildVariant({ output: options.output, variant, skillText }));
}

if (import.meta.main) {
  const [output, skillFile] = process.argv.slice(2);
  const roots = prepare({
    output: output ?? defaultOutputDirectory(),
    skillFile: skillFile ?? defaultSkillFile,
  });

  process.stdout.write(`${roots.join("\n")}\n`);
}
