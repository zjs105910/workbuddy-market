import { analyzeReview, readReviewSkill, type ReviewModel } from "../analyze";
import { checkDispositions, type DispositionCheck, reviewCandidates } from "../candidates";
import { correctionPrompt } from "../correction";
import { cachedFetch, type EvidenceGate, gateFindings } from "../evidence";
import { type ReviewPacket, reviewPrompt } from "../packet";
import { reviewResult } from "../result";
import type { Analysis, ReviewResult } from "../types";
import type { ChecksFile, PacketFile } from "./schemas";

type Judged = { readonly gate: EvidenceGate; readonly dispositions: DispositionCheck };

function sumCosts(costs: readonly (number | null)[]): number | null {
  const known = costs.filter((cost): cost is number => cost !== null);

  return known.length === 0 ? null : known.reduce((total, cost) => total + cost, 0);
}

function rejections(judged: Judged): readonly string[] {
  return [
    ...judged.gate.dropped.map((entry) => `Finding "${entry.title}" at ${entry.path}:${entry.line}: ${entry.reason}.`),
    ...judged.dispositions.problems,
  ];
}

export async function analyzeStage(options: {
  readonly packet: PacketFile;
  readonly checks: ChecksFile | null;
  readonly checkout: string;
  readonly reviewModel: ReviewModel;
  readonly fetchText?: (url: string) => Promise<string | null>;
}): Promise<ReviewResult> {
  const startedAt = Date.now();
  const { packet, checks } = options;

  if (checks !== null && checks.headSha !== packet.context.facts.headSha) {
    throw new Error("The toolchain results belong to a different head commit.");
  }

  const reviewPacket: ReviewPacket = {
    context: packet.context,
    ruleHits: packet.ruleHits,
    toolchain: [...packet.reports, ...(checks?.reports ?? [])],
  };
  const candidates = reviewCandidates(reviewPacket);
  const skill = await readReviewSkill();
  const fetchText = cachedFetch(options.fetchText);
  const judge = async (output: Analysis): Promise<Judged> => ({
    gate: await gateFindings({
      findings: output.findings,
      sources: { checkout: options.checkout, files: packet.context.files, ruleHits: packet.ruleHits, toolchain: reviewPacket.toolchain, fetchText },
    }),
    dispositions: checkDispositions({ findings: output.findings, dropped: output.dropped, candidates }),
  });
  const run = (prompt: string) => analyzeReview({ reviewModel: options.reviewModel, checkout: options.checkout, prompt });
  const first = await run(reviewPrompt({ skill, packet: reviewPacket, candidates }));
  const firstJudged = await judge(first.output);
  const problems = rejections(firstJudged);
  const second =
    problems.length === 0
      ? null
      : await run(correctionPrompt({ skill, packet: reviewPacket, candidates, previous: first.output, rejections: problems })).catch(
          () => "failed" as const,
        );
  const final = second === null || second === "failed" ? { run: first, judged: firstJudged } : { run: second, judged: await judge(second.output) };

  return reviewResult({
    packet: reviewPacket,
    analysis: final.run.output,
    gate: final.judged.gate,
    dispositions: final.judged.dispositions,
    candidates,
    model: options.reviewModel.model,
    costUsd: sumCosts([first.costUsd, ...(second !== null && second !== "failed" ? [second.costUsd] : [])]),
    correctionRound: second === null ? "none" : second === "failed" ? "failed" : "ran",
    rejections: problems,
    startedAt,
  });
}
