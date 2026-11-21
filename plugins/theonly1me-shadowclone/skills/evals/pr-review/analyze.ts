import { z } from "zod";
import { labels } from "./judge/prompt";

const answerSchema = z.object({
  judge: z.string(),
  output: z.object({ findings: z.array(z.object({ id: z.string(), label: z.enum(labels) })), detected: z.array(z.string()) }).nullable(),
});

export const judgedCaseSchema = z.object({
  caseId: z.string(),
  kind: z.enum(["defect", "clean"]),
  findings: z.array(z.object({ id: z.string(), arm: z.string() })),
  answers: z.array(answerSchema),
});

type JudgedCase = z.infer<typeof judgedCaseSchema>;
type FinalLabel = (typeof labels)[number] | "disputed";

export function finalLabels(options: { readonly judged: JudgedCase; readonly tiebreaks: ReadonlyMap<string, string> }): ReadonlyMap<string, FinalLabel> {
  const [first, second] = options.judged.answers.map((answer) => new Map((answer.output?.findings ?? []).map((finding) => [finding.id, finding.label])));

  return new Map(
    options.judged.findings.map((finding) => {
      const one = first?.get(finding.id);
      const two = second?.get(finding.id);
      const tiebreak = labels.find((label) => label === options.tiebreaks.get(finding.id));

      return [finding.id, one !== undefined && one === two ? one : (tiebreak ?? "disputed")];
    }),
  );
}

export function detectedIds(judged: JudgedCase): ReadonlySet<string> {
  const [first, second] = judged.answers.map((answer) => new Set(answer.output?.detected ?? []));

  return new Set([...(first ?? [])].filter((id) => second?.has(id) === true));
}

function seededRandom(seed: number): () => number {
  let state = seed;

  return () => {
    state = (state * 1_103_515_245 + 12_345) % 2_147_483_648;
    return state / 2_147_483_648;
  };
}

export function bootstrapInterval(options: {
  readonly cases: readonly { readonly numerator: number; readonly denominator: number }[];
  readonly seed: number;
}): readonly [number, number] | null {
  const random = seededRandom(options.seed);
  const rates: number[] = [];

  for (let sample = 0; sample < 10_000; sample += 1) {
    let numerator = 0;
    let denominator = 0;

    for (let draw = 0; draw < options.cases.length; draw += 1) {
      const picked = options.cases[Math.floor(random() * options.cases.length)];
      numerator += picked?.numerator ?? 0;
      denominator += picked?.denominator ?? 0;
    }

    if (denominator > 0) {
      rates.push(numerator / denominator);
    }
  }

  rates.sort((left, right) => left - right);
  const low = rates[Math.floor(rates.length * 0.025)];
  const high = rates[Math.floor(rates.length * 0.975)];

  return low === undefined || high === undefined ? null : [low, high];
}
