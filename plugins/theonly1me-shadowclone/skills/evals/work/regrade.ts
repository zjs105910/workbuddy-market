import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { caseById } from "./cases";
import { gradeRun } from "./grade/index";
import { bashCommands, type TraceTurn } from "./grade/trace";

const rowSchema = z.looseObject({
  prompt_id: z.string(),
  rep: z.number(),
  grade: z.record(z.string(), z.number()),
  meta: z.looseObject({}),
});

const turnSchema = z.array(
  z.object({ role: z.enum(["user", "assistant", "tool_call", "tool_result"]), content: z.string(), name: z.string().optional() }),
);

export function regradeVariant(directory: string): void {
  const file = path.join(directory, "results.jsonl");
  const rows = readFileSync(file, "utf8")
    .split("\n")
    .filter((line) => line.trim().length > 0)
    .map((line) => rowSchema.parse(JSON.parse(line)));
  const regraded = rows.map((row) => {
    const id = `${row.prompt_id}_rep${row.rep}`;
    const turns: readonly TraceTurn[] = turnSchema.parse(JSON.parse(readFileSync(path.join(directory, "traces", `${id}.json`), "utf8")));
    const grade = gradeRun({ root: path.join(directory, "graded", id), definition: caseById(row.prompt_id), commands: bashCommands(turns) });

    return { ...row, grade: { ...grade.grade, report: row.grade.report ?? 0 }, meta: { ...row.meta, failures: grade.failures, threads: grade.threads } };
  });

  writeFileSync(file, `${regraded.map((row) => JSON.stringify(row)).join("\n")}\n`);
}

if (import.meta.main) {
  for (const directory of process.argv.slice(2)) {
    regradeVariant(directory);
    process.stdout.write(`regraded ${directory}\n`);
  }
}
