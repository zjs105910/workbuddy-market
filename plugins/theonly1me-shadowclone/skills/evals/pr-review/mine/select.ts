import type { UpstreamPull } from "./pulls";

export type DefectCase = {
  readonly kind: "defect";
  readonly introducing: number;
  readonly fix: number;
  readonly fixCommit: string;
  readonly blamedLines: number;
};

export type CleanCase = { readonly kind: "clean"; readonly introducing: number };

const fixTitle = /^(fix|revert)(\([^)]*\))?!?:|^Revert "|\bregression\b/i;
const codeChangeTitle = /^(feat|fix|perf|refactor)(\([^)]*\))?!?:/i;
const day = 86_400_000;

export function isFix(pull: UpstreamPull): boolean {
  return fixTitle.test(pull.title) && pull.user.type !== "Bot";
}

export function isReviewable(pull: UpstreamPull): boolean {
  const size = pull.additions + pull.deletions;

  return pull.user.type !== "Bot" && size >= 5 && size <= 1_500 && pull.changed_files <= 40 && codeChangeTitle.test(pull.title);
}

export function revertedPull(pull: UpstreamPull): number | null {
  if (!/^revert/i.test(pull.title)) {
    return null;
  }

  const number = Number(/#(\d+)/.exec(`${pull.title} ${pull.body ?? ""}`)?.[1]);

  return Number.isInteger(number) && number > 0 ? number : null;
}

export function pickIntroducing(options: {
  readonly fix: UpstreamPull;
  readonly blamed: ReadonlyMap<number, number>;
  readonly pulls: ReadonlyMap<number, UpstreamPull>;
  readonly introducedBefore: string;
  readonly fixWithinDays: number;
}): DefectCase | null {
  const { fix } = options;
  const fixTime = Date.parse(fix.merged_at ?? "");
  const reverted = revertedPull(fix);
  const ranked = reverted !== null ? [[reverted, 1] as const] : [...options.blamed.entries()].sort((left, right) => right[1] - left[1]);

  for (const [number, blamedLines] of ranked) {
    const introducing = options.pulls.get(number);
    const introducedTime = Date.parse(introducing?.merged_at ?? "");

    if (
      introducing !== undefined &&
      number !== fix.number &&
      isReviewable(introducing) &&
      introducedTime < fixTime &&
      fixTime - introducedTime <= options.fixWithinDays * day &&
      (introducing.merged_at ?? "") < options.introducedBefore
    ) {
      return { kind: "defect", introducing: number, fix: fix.number, fixCommit: fix.merge_commit_sha ?? "", blamedLines };
    }
  }

  return null;
}
