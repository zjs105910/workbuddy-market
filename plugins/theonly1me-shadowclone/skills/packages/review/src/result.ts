import type { DispositionCheck, ReviewCandidate } from "./candidates";
import type { EvidenceGate } from "./evidence";
import { packetDiff, type ReviewPacket } from "./packet";
import { rankFindings } from "./rank";
import type { RuleHit } from "./rules";
import { type Analysis, type Finding, type ReviewResult, reviewResultSchema } from "./types";

function certainFinding(hit: RuleHit): Finding {
  return {
    path: hit.path,
    line: hit.line,
    severity: hit.severity,
    category: hit.category,
    source: "rule",
    title: hit.title,
    explanation: hit.detail ?? `The built-in rule \`${hit.ruleId}\` matched an added line.`,
    failureScenario: hit.failure,
    evidence: [
      { source: "rule", location: `${hit.path}:${hit.line}`, quote: hit.ruleId },
      ...(hit.reference === undefined ? [] : [{ source: "doc" as const, location: hit.reference, quote: hit.ruleId }]),
    ],
    rule: null,
    suggestion: null,
    refutation: "A certain check. It is reported without model judgment.",
    candidates: [],
  };
}

function candidateDecisions(options: {
  readonly gate: EvidenceGate;
  readonly dispositions: DispositionCheck;
  readonly candidates: readonly ReviewCandidate[];
}) {
  const byId = new Map(options.candidates.map((candidate) => [candidate.id, candidate]));
  const lostWithFinding = options.gate.dropped.flatMap((finding) =>
    finding.candidates.flatMap((id) => {
      const candidate = byId.get(id);

      return candidate ? [{ ...candidate, reason: `its finding failed the evidence check: ${finding.reason}`.slice(0, 300) }] : [];
    }),
  );

  return {
    dropped: [...options.dispositions.dropped, ...lostWithFinding]
      .map(({ id, title, path, line, reason }) => ({ id, title, path, line, reason }))
      .slice(0, 220),
    undecided: options.dispositions.undecided.map(({ id, title, path, line }) => ({ id, title, path, line })).slice(0, 220),
  };
}

export function reviewResult(options: {
  readonly packet: ReviewPacket;
  readonly analysis: Analysis;
  readonly gate: EvidenceGate;
  readonly dispositions: DispositionCheck;
  readonly candidates: readonly ReviewCandidate[];
  readonly model: string;
  readonly costUsd: number | null;
  readonly correctionRound: ReviewResult["statistics"]["correctionRound"];
  readonly rejections: readonly string[];
  readonly startedAt: number;
}): ReviewResult {
  const { packet, gate } = options;
  const certainHits = packet.ruleHits.filter((hit) => hit.level === "certain");

  return reviewResultSchema.parse({
    version: 1,
    pull: packet.context.facts,
    model: options.model,
    findings: rankFindings([...certainHits.map(certainFinding), ...gate.kept]),
    commentableLines: Object.fromEntries(packet.context.files.map((file) => [file.path, file.ranges])),
    skippedPaths: packetDiff(packet.context.files).generated,
    toolchain: packet.toolchain.map((report) => ({
      stack: report.stack,
      tool: report.tool,
      status: report.status,
      detail: report.detail.slice(0, 1000),
      newDiagnostics: report.diagnostics.length,
    })),
    dropped: gate.dropped.slice(0, 20).map(({ title, path, line, reason }) => ({ title, path, line, reason })),
    candidates: candidateDecisions({ gate, dispositions: options.dispositions, candidates: options.candidates }),
    rejections: options.rejections.slice(0, 50).map((rejection) => rejection.slice(0, 600)),
    statistics: {
      modelFindings: options.analysis.findings.length,
      droppedForEvidence: gate.dropped.length,
      correctionRound: options.correctionRound,
      certainRuleHits: certainHits.length,
      signalRuleHits: packet.ruleHits.length - certainHits.length,
      durationMilliseconds: Date.now() - options.startedAt,
      costUsd: options.costUsd,
    },
  });
}
