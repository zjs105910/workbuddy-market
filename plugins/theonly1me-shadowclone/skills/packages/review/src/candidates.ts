import type { ReviewPacket } from "./packet";
import type { Finding } from "./types";

export type ReviewCandidate = {
  readonly id: string;
  readonly kind: "rule" | "toolchain";
  readonly path: string;
  readonly line: number;
  readonly title: string;
};

export type DecidedCandidate = ReviewCandidate & { readonly reason: string };

export type DispositionCheck = {
  readonly problems: readonly string[];
  readonly dropped: readonly DecidedCandidate[];
  readonly undecided: readonly ReviewCandidate[];
};

export function reviewCandidates(packet: ReviewPacket): readonly ReviewCandidate[] {
  const signals = packet.ruleHits
    .filter((hit) => hit.level === "signal")
    .map((hit, index) => ({ id: `S${index + 1}`, kind: "rule" as const, path: hit.path, line: hit.line, title: `${hit.ruleId}: ${hit.title}` }));
  const diagnostics = packet.toolchain
    .flatMap((report) => report.diagnostics)
    .map((diagnostic, index) => ({
      id: `T${index + 1}`,
      kind: "toolchain" as const,
      path: diagnostic.path,
      line: diagnostic.line,
      title: `${diagnostic.tool}: ${diagnostic.message}`.slice(0, 200),
    }));

  return [...signals, ...diagnostics];
}

export function checkDispositions(options: {
  readonly findings: readonly Finding[];
  readonly dropped: readonly { readonly id: string; readonly reason: string }[];
  readonly candidates: readonly ReviewCandidate[];
}): DispositionCheck {
  const known = new Map(options.candidates.map((candidate) => [candidate.id, candidate]));
  const decisions = [...options.findings.flatMap((finding) => finding.candidates), ...options.dropped.map((entry) => entry.id)];
  const counts = new Map<string, number>();

  for (const id of decisions) {
    counts.set(id, (counts.get(id) ?? 0) + 1);
  }

  const unknown = [...counts.keys()].filter((id) => !known.has(id));
  const repeated = [...counts.entries()].filter(([id, count]) => count > 1 && known.has(id)).map(([id]) => id);
  const undecided = options.candidates.filter((candidate) => !counts.has(candidate.id));
  const problems = [
    ...(unknown.length > 0 ? [`${unknown.join(", ")} are not candidate ids in the packet.`] : []),
    ...(repeated.length > 0 ? [`${repeated.join(", ")} have more than one decision. Raise each id in one finding or drop it once.`] : []),
    ...(undecided.length > 0 ? [`${undecided.map((candidate) => candidate.id).join(", ")} have no decision. Raise each one in a finding or drop it with a reason.`] : []),
  ];
  const dropped = options.dropped.flatMap((entry) => {
    const candidate = known.get(entry.id);

    return candidate ? [{ ...candidate, reason: entry.reason }] : [];
  });

  return { problems, dropped, undecided };
}
