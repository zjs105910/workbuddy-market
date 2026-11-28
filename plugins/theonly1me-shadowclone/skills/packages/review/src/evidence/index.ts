import type { Finding } from "../types";
import { fetchPageText } from "./fetchPage";
import { checkEvidence, findingLocationExists, readHeadLines, type EvidenceSources } from "./verify";

export type { EvidenceSources } from "./verify";
export { fetchPageText } from "./fetchPage";

export type DroppedFinding = {
  readonly title: string;
  readonly path: string;
  readonly line: number;
  readonly reason: string;
  readonly candidates: readonly string[];
};

export type EvidenceGate = {
  readonly kept: readonly Finding[];
  readonly dropped: readonly DroppedFinding[];
};

const maximumFetchedPages = 10;

export function cachedFetch(fetchText: (url: string) => Promise<string | null> = fetchPageText): (url: string) => Promise<string | null> {
  const pages = new Map<string, Promise<string | null>>();

  return (url) => {
    const cached = pages.get(url);

    if (cached !== undefined) {
      return cached;
    }

    const page = pages.size < maximumFetchedPages ? fetchText(url) : Promise.resolve(null);
    pages.set(url, page);
    return page;
  };
}

async function gateFinding(options: { readonly finding: Finding; readonly sources: EvidenceSources }): Promise<Finding | DroppedFinding> {
  const { finding, sources } = options;
  const dropped = (reason: string): DroppedFinding => ({ title: finding.title, path: finding.path, line: finding.line, reason, candidates: finding.candidates });
  const deletedFile = sources.files.some((file) => file.path === finding.path && file.deleted);
  const lines = await readHeadLines({ checkout: sources.checkout, relativePath: finding.path });

  if (!deletedFile && !findingLocationExists({ finding, lines })) {
    return dropped(`\`${finding.path}:${finding.line}\` does not exist at the head`);
  }

  const results = await Promise.all(finding.evidence.map(async (item) => ({ item, check: await checkEvidence({ item, sources }) })));
  const failedCode = results.find(({ item, check }) => item.source !== "doc" && !check.verified);

  if (failedCode !== undefined && !failedCode.check.verified) {
    return dropped(failedCode.check.reason);
  }

  const evidence = results.filter(({ check }) => check.verified).map(({ item }) => item);

  if (!evidence.some((item) => item.source !== "doc")) {
    return dropped("no evidence points at the code or the diff");
  }

  return { ...finding, evidence };
}

export async function gateFindings(options: { readonly findings: readonly Finding[]; readonly sources: EvidenceSources }): Promise<EvidenceGate> {
  const outcomes = await Promise.all(options.findings.map((finding) => gateFinding({ finding, sources: options.sources })));

  return {
    kept: outcomes.filter((outcome): outcome is Finding => !("reason" in outcome)),
    dropped: outcomes.filter((outcome): outcome is DroppedFinding => "reason" in outcome),
  };
}
