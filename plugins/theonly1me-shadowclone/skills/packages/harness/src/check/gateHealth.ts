import path from "node:path";
import { z } from "zod";
import { readLocalText } from "@shadowclone/core";
import type { HarnessManifest } from "@shadowclone/environment";
import type { HarnessFinding } from "./types";
import { error, warning, refresh } from "./healthFinding";

const packageScriptsSchema = z.object({
  scripts: z.record(z.string(), z.string()).optional(),
});

async function packageScripts(
  root: string,
): Promise<Readonly<Record<string, string>>> {
  const text = await readLocalText(path.join(root, "package.json"));

  if (text === null) {
    return {};
  }

  try {
    return packageScriptsSchema.parse(JSON.parse(text)).scripts ?? {};
  } catch {
    return {};
  }
}

export async function gateFindings(options: {
  readonly root: string;
  readonly manifest: HarnessManifest;
}): Promise<readonly HarnessFinding[]> {
  const gate = options.manifest.gate;

  if (gate === null) {
    return [
      warning({
        rule: "gate-missing",
        path: ".shadowclone/harness.json",
        fix: `No gate was detected. Add a check script, then ${refresh}.`,
      }),
    ];
  }

  const scripts = [
    ...gate.command.matchAll(
      /(?:^|&&\s*)(?:(?:bun|npm|pnpm) run|yarn) ([\w:.-]+)/g,
    ),
  ].map((match) => match[1] ?? "");
  const declared =
    scripts.length === 0 ? {} : await packageScripts(options.root);
  const missing = scripts.filter((script) => !(script in declared));
  const findings = missing.map((script) =>
    error({
      rule: "gate-script",
      path: "package.json",
      fix: `The gate runs \`${gate.command}\`, but package.json has no \`${script}\` script. Restore it or ${refresh}.`,
    }),
  );

  const workflows = await Array.fromAsync(
    new Bun.Glob(".github/workflows/*.{yml,yaml}").scan({
      cwd: options.root,
      dot: true,
    }),
  );
  const texts = await Promise.all(
    workflows.map((workflow) =>
      Bun.file(path.join(options.root, workflow)).text(),
    ),
  );

  if (!texts.some((workflowText) => workflowText.includes(gate.command))) {
    findings.push(
      warning({
        rule: "gate-ci",
        path: ".github/workflows",
        fix: `CI does not run \`${gate.command}\`. Add it to a workflow so every agent's change meets the same gate.`,
      }),
    );
  }

  return findings;
}
