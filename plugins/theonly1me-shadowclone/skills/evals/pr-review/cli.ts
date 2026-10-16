import { armNames, localArmNames, runArm, runLocalArm } from "./arms";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { judgedCaseSchema } from "./analyze";
import { collectFindings } from "./collect";
import { copyCases } from "./copy";
import { judgeAll } from "./judge";
import { upstreamPullSchema } from "./mine/pulls";
import { prepareCases } from "./prepare";
import { armMetrics, metricsTable } from "./report";
import { evalCaseSchema, sampleCases } from "./sample";
import { validateDefects } from "./validate";

function option(name: string): string {
  const index = process.argv.indexOf(name);
  const value = index < 0 ? undefined : process.argv[index + 1];

  if (value === undefined) {
    throw new Error(`Missing ${name}`);
  }

  return value;
}

const [command] = process.argv.slice(2);

if (command === "validate") {
  await validateDefects({ mined: option("--mined"), clone: option("--clone") });
} else if (command === "sample") {
  const selected = sampleCases({ mined: option("--mined"), clean: Number(option("--clean")), seed: Number(option("--seed")) });
  console.log(`${selected.length} cases: ${selected.filter((entry) => entry.kind === "defect").length} defect, ${selected.filter((entry) => entry.kind === "clean").length} clean`);
} else if (command === "copy") {
  const onlyIndex = process.argv.indexOf("--only");
  const only = onlyIndex < 0 ? undefined : (process.argv[onlyIndex + 1] ?? "").split(",");
  const copied = await copyCases({ mined: option("--mined"), clone: option("--clone"), evalRepository: option("--eval-repo"), ...(only === undefined ? {} : { only }) });
  console.log(`${copied.length} cases copied`);
} else if (command === "prepare") {
  const prepared = await prepareCases({ mined: option("--mined"), clone: option("--clone"), casesDirectory: option("--cases-dir") });
  console.log(`${prepared.length} cases prepared`);
} else if (command === "run") {
  const arm = armNames.find((name) => name === option("--arm"));
  const localArm = localArmNames.find((name) => name === arm);
  const onlyIndex = process.argv.indexOf("--only");
  const only = onlyIndex < 0 ? undefined : (process.argv[onlyIndex + 1] ?? "").split(",");

  if (arm === undefined) {
    throw new Error(`Choose --arm from ${armNames.join(", ")}`);
  }

  if (localArm !== undefined) {
    const runs = await runLocalArm({ arm: localArm, mined: option("--mined"), runs: option("--runs"), clone: option("--clone"), model: option("--model"), ...(only === undefined ? {} : { only }) });
    console.log(`${arm}: ${runs.filter((run) => run.status === "done").length} of ${runs.length} done`);
    process.exit(0);
  }

  const runs = await runArm({
    arm,
    mined: option("--mined"),
    runs: option("--runs"),
    evalRepository: option("--eval-repo"),
    checkout: option("--checkout"),
    model: option("--model"),
    ...(only === undefined ? {} : { only }),
  });
  console.log(`${arm}: ${runs.filter((run) => run.status === "done").length} of ${runs.length} done`);
} else if (command === "judge" || command === "report") {
  const mined = option("--mined");
  const cases = z.array(evalCaseSchema).parse(JSON.parse(readFileSync(path.join(mined, option("--cases")), "utf8")));
  const { findingsByCase, summaries } = collectFindings({ runs: option("--runs"), caseIds: cases.map((entry) => entry.id) });
  const judgedFile = path.join(option("--runs"), "judged.json");

  if (command === "judge") {
    const pulls = z.array(upstreamPullSchema).parse(JSON.parse(readFileSync(path.join(mined, "pulls.json"), "utf8")));
    const fixCommits = new Map(pulls.flatMap((pull) => (pull.merge_commit_sha === null ? [] : [[pull.number, pull.merge_commit_sha] as const])));

    await judgeAll({ mined, cases, clone: option("--clone"), findingsByCase, output: judgedFile, seed: option("--seed"), fixCommits });
  }

  const tiebreakFile = path.join(option("--runs"), "tiebreaks.json");
  const tiebreaks = new Map(existsSync(tiebreakFile) ? Object.entries(z.record(z.string(), z.string()).parse(JSON.parse(readFileSync(tiebreakFile, "utf8")))) : []);
  const judged = z.array(judgedCaseSchema).parse(JSON.parse(readFileSync(judgedFile, "utf8")));
  const metrics = armMetrics({ judged, summaries, tiebreaks, seed: Number(option("--seed")) });

  writeFileSync(path.join(option("--runs"), "metrics.json"), JSON.stringify(metrics, null, 2));
  console.log(metricsTable(metrics));
} else {
  throw new Error("Use bun evals/pr-review/cli.ts validate|sample|copy|prepare|run|judge|report with their options");
}
