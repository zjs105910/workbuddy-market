import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { z } from "zod";
import { upstreamPullSchema } from "./mine/pulls";

export const selectedCaseSchema = z.object({
  id: z.string().regex(/^c\d{2}$/),
  kind: z.enum(["defect", "clean"]),
  upstream: z.number(),
  title: z.string(),
  fix: z.number().nullable(),
  defect: z.string().nullable(),
});

export type SelectedCase = z.infer<typeof selectedCaseSchema>;

export const evalCaseSchema = selectedCaseSchema.extend({ baseSha: z.string(), headSha: z.string() });

export type EvalCase = z.infer<typeof evalCaseSchema>;

function seededShuffle<Item>(options: { readonly items: readonly Item[]; readonly seed: number }): readonly Item[] {
  const shuffled = [...options.items];
  let state = options.seed;

  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    state = (state * 1_103_515_245 + 12_345) % 2_147_483_648;
    const swap = state % (index + 1);
    const current = shuffled[index];
    const other = shuffled[swap];

    if (current !== undefined && other !== undefined) {
      shuffled[index] = other;
      shuffled[swap] = current;
    }
  }

  return shuffled;
}

const validatedSchema = z.array(
  z.object({
    introducing: z.number(),
    fix: z.number(),
    valid: z.boolean(),
    verdicts: z.array(z.object({ output: z.object({ defect: z.string() }).nullable() })),
  }),
);

export function sampleCases(options: { readonly mined: string; readonly clean: number; readonly seed: number }): readonly SelectedCase[] {
  const pulls = new Map(z.array(upstreamPullSchema).parse(JSON.parse(readFileSync(path.join(options.mined, "pulls.json"), "utf8"))).map((pull) => [pull.number, pull]));
  const validated = validatedSchema.parse(JSON.parse(readFileSync(path.join(options.mined, "validated.json"), "utf8"))).filter((entry) => entry.valid);
  const cleanPool = z.object({ clean: z.array(z.object({ introducing: z.number() })) }).parse(JSON.parse(readFileSync(path.join(options.mined, "cases.json"), "utf8"))).clean;
  const defects = validated.map((entry) => ({ kind: "defect" as const, upstream: entry.introducing, fix: entry.fix, defect: entry.verdicts[0]?.output?.defect ?? null }));
  const clean = seededShuffle({ items: cleanPool, seed: options.seed })
    .slice(0, options.clean)
    .map((entry) => ({ kind: "clean" as const, upstream: entry.introducing, fix: null, defect: null }));
  const ordered = seededShuffle({ items: [...defects, ...clean], seed: options.seed + 1 });
  const selected = ordered.map((entry, index) => ({ ...entry, id: `c${String(index + 1).padStart(2, "0")}`, title: pulls.get(entry.upstream)?.title ?? "" }));

  writeFileSync(path.join(options.mined, "selected.json"), JSON.stringify(selected, null, 2));
  return selected;
}
