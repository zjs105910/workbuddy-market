import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { caseById } from "./cases";
import { copyForGrading, readTrace } from "./grade/collect";
import { gradeRun, metricIds } from "./grade/index";
import { bashCommands, parseTrace } from "./grade/trace";
import { dockerConfigLinks, dockerLinksMessage } from "./preflight";
import { defaultOutputDirectory, defaultSkillFile, prepare, type VariantName, variantNames } from "./prepare";

const runSchema = z.looseObject({
  score: z.number(),
  turns: z.number(),
  costUsd: z.number(),
  judgeCostUsd: z.number(),
  durationSeconds: z.number(),
  error: z.string().nullable(),
  tracePath: z.string(),
  graders: z.array(z.looseObject({ name: z.string(), passed: z.boolean().optional() })),
});

const resultSchema = z.looseObject({
  costUsd: z.number(),
  durationSeconds: z.number(),
  cases: z.array(z.looseObject({ name: z.string(), arms: z.looseObject({ with: z.array(runSchema) }) })),
});


function option(name: string, fallback: string): string {
  const index = process.argv.indexOf(name);

  return index >= 0 ? (process.argv[index + 1] ?? fallback) : fallback;
}

async function runVariant(options: {
  readonly root: string;
  readonly variant: VariantName;
  readonly runs: number;
  readonly concurrency: number;
  readonly cases: string | undefined;
  readonly output: string;
}): Promise<string> {
  const json = path.join(options.output, `plugin-eval-${options.variant}-${Date.now()}.json`);
  const command = [
    "claude", "plugin", "eval", options.root,
    "--runs", String(options.runs), "--ablation", "none", "-j", String(options.concurrency),
    "--model", "claude-sonnet-5-5", "--judge-model", "claude-opus-5-5",
    "--scaffold", "--keep-temp", "--trust-plugin", "--no-publish",
    ...(options.cases === undefined ? [] : ["--case", options.cases]),
    "--allow-tools", "Bash", "Edit", "Write",
    "--json", json,
  ];
  const child = Bun.spawn({ cmd: command, cwd: options.root, stdout: "pipe", stderr: "pipe" });
  const log = await new Response(child.stderr).text();

  writeFileSync(path.join(options.output, `plugin-eval-${options.variant}.log`), `${await new Response(child.stdout).text()}\n${log}`);
  await child.exited;

  return json;
}

function writeVariant(options: { readonly flow: string; readonly label: string; readonly json: string }): void {
  const directory = path.join(options.flow, options.label);
  const result = resultSchema.parse(JSON.parse(readFileSync(options.json, "utf8")));

  mkdirSync(path.join(directory, "traces"), { recursive: true });

  for (const entry of result.cases) {
    const definition = caseById(entry.name);

    entry.arms.with.forEach((run, rep) => {
      const id = `${entry.name}_rep${rep}`;
      const raw = readTrace(run.tracePath);
      const turns = parseTrace(raw);

      writeFileSync(path.join(directory, "traces", `${id}.json`), `${JSON.stringify(turns, null, 2)}\n`);

      const keptDirectory = run.tracePath === "" ? "" : path.dirname(path.dirname(run.tracePath));
      const graded = keptDirectory === "" ? null : copyForGrading({ keptDirectory, target: path.join(directory, "graded", id) });

      if (run.error !== null || graded === null) {
        appendFileSync(path.join(directory, "errors.jsonl"), `${JSON.stringify({ prompt_id: entry.name, rep, class: run.error === null ? "harness" : "run-error", error: run.error, cost_usd: run.costUsd + run.judgeCostUsd })}\n`);
        return;
      }

      const grade = gradeRun({ root: graded, definition, commands: bashCommands(turns) });
      const report = run.graders.find((grader) => grader.name === "report")?.passed === true ? 1 : 0;

      appendFileSync(
        path.join(directory, "results.jsonl"),
        `${JSON.stringify({
          prompt_id: entry.name,
          rep,
          prompt: definition.prompt,
          split: definition.split,
          tags: [definition.tags[0], ...definition.tags.slice(1)],
          status: "ok",
          model: "claude-sonnet-5-5",
          grade: { ...grade.grade, report },
          cost_usd: run.costUsd + run.judgeCostUsd,
          turns: run.turns,
          latency_s: run.durationSeconds,
          gh_calls: grade.ghCalls,
          unsupported_gh: grade.unsupportedGh,
          meta: { failures: grade.failures, threads: grade.threads, kept: keptDirectory },
        })}\n`,
      );
    });
  }
}

function writeState(flow: string): void {
  const file = path.join(flow, "_state.json");

  if (existsSync(file)) {
    return;
  }

  writeFileSync(
    file,
    `${JSON.stringify(
      {
        flow: "shadowclone-work",
        metrics: [
          ...metricIds.map((id) => ({ id, label: id, kind: id === "comments" ? "float" : "binary" })),
          { id: "report", label: "report", kind: "judge" },
        ],
        perf_fields: [
          { id: "cost_usd", label: "cost", unit: "$" },
          { id: "turns", label: "turns" },
          { id: "latency_s", label: "time", unit: "s" },
          { id: "gh_calls", label: "gh calls" },
          { id: "unsupported_gh", label: "gh gaps" },
        ],
      },
      null,
      2,
    )}\n`,
  );
}

if (import.meta.main) {
  const outputRoot = option("--output", path.dirname(defaultOutputDirectory()));
  const flow = option("--flow", path.join(outputRoot, "flow"));
  const links = process.argv.includes("--skip-docker-check") ? [] : dockerConfigLinks();

  if (links.length > 0) {
    process.stderr.write(`${dockerLinksMessage(links)}\n`);
    process.exit(1);
  }

  const variants = option("--variants", variantNames.join(",")).split(",").filter((name): name is VariantName => variantNames.some((known) => known === name));
  const runs = Number(option("--runs", "2"));
  const baselineRuns = Number(option("--baseline-runs", "1"));
  const concurrency = Number(option("--concurrency", "4"));
  const casesOption = option("--cases", "");
  const roots = prepare({ output: path.join(outputRoot, "build"), skillFile: option("--skill", defaultSkillFile) });

  mkdirSync(flow, { recursive: true });
  writeState(flow);

  const outputs = await Promise.all(
    variants.map(async (variant) => ({
      variant,
      json: await runVariant({
        root: roots[variantNames.indexOf(variant)] ?? "",
        variant,
        runs: variant === "baseline" ? baselineRuns : runs,
        concurrency,
        cases: casesOption === "" ? undefined : casesOption,
        output: flow,
      }),
    })),
  );

  const labels: Readonly<Record<VariantName, string>> = { baseline: "baseline", "skill-only": option("--skill-label", "v1") };

  for (const output of outputs) {
    writeVariant({ flow, label: labels[output.variant], json: output.json });
  }

  process.stdout.write(`${flow}\n`);
}
