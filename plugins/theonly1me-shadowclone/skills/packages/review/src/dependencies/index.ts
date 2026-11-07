import type { DiffFile } from "../collect";
import { readGit } from "../collect/git";
import type { RuleHit } from "../rules";
import type { CommandReport } from "../toolchain";
import { lockfileParser } from "./lockfiles";
import { type Advisory, findAdvisories, type JsonRequest, osvRequest } from "./osv";
import { type LockedPackage, packageKey } from "./types";

export type DependencyCheck = {
  readonly hits: readonly RuleHit[];
  readonly reports: readonly CommandReport[];
};

const maximumPackages = 1_000;
const maximumHits = 20;

type ChangedPackage = LockedPackage & { readonly path: string; readonly line: number };

export function lineOf(options: { readonly text: string; readonly name: string; readonly version: string }): number {
  const lines = options.text.split("\n");
  const nameIndex = lines.findIndex((line) => line.includes(options.name));

  if (nameIndex < 0) {
    return 1;
  }

  const versionOffset = lines.slice(nameIndex, nameIndex + 8).findIndex((line) => line.includes(options.version));

  return nameIndex + (versionOffset < 0 ? 0 : versionOffset) + 1;
}

async function changedPackages(options: {
  readonly checkout: string;
  readonly baseSha: string;
  readonly headSha: string;
  readonly files: readonly DiffFile[];
}): Promise<readonly ChangedPackage[]> {
  const changed = new Map<string, ChangedPackage>();

  for (const file of options.files.filter((entry) => !entry.deleted)) {
    const parse = lockfileParser(file.path);

    if (parse === null) {
      continue;
    }

    const read = (sha: string) => readGit({ checkout: options.checkout, arguments: ["show", `${sha}:${file.path}`] }).catch(() => "");
    const headText = await read(options.headSha);
    const before = new Set(parse(await read(options.baseSha)).map(packageKey));

    for (const lockedPackage of parse(headText)) {
      const key = packageKey(lockedPackage);

      if (!before.has(key) && !changed.has(key)) {
        changed.set(key, { ...lockedPackage, path: file.path, line: lineOf({ text: headText, name: lockedPackage.name, version: lockedPackage.version }) });
      }
    }
  }

  return [...changed.values()].slice(0, maximumPackages);
}

const severityRank: Readonly<Record<RuleHit["severity"], number>> = { high: 0, medium: 1, low: 2 };

function sentence(text: string): string {
  return `${text.trim().replace(/[.\s]*$/, "")}.`;
}

function packageHit(options: { readonly changed: ChangedPackage; readonly advisories: readonly Advisory[] }): RuleHit | null {
  const { changed } = options;
  const advisories = [...options.advisories].sort((left, right) => severityRank[left.severity] - severityRank[right.severity]);
  const [worst] = advisories;

  if (worst === undefined) {
    return null;
  }

  const fixed = [...new Set(advisories.flatMap((advisory) => advisory.fixedVersions))];
  const fix = fixed.length > 0 ? `Fixed versions: ${fixed.join(", ")}.` : "No fixed version is listed.";
  const entries = advisories.map((advisory) => `${advisory.id} (${advisory.severity}): ${sentence(advisory.summary)}`);
  const budget = 300 - fix.length - 30;
  const shown = entries.filter((_, index) => entries.slice(0, index + 1).join(" ").length <= budget);
  const hidden = entries.length - shown.length;
  const listed = [...(shown.length > 0 ? shown : [worst.id]), ...(hidden > 0 ? [`${hidden} more on osv.dev.`] : [])].join(" ");

  return {
    ruleId: worst.id,
    level: "certain",
    severity: worst.severity,
    category: "security",
    title: `${advisories.length === 1 ? "Known vulnerability" : `${advisories.length} known vulnerabilities`} in ${changed.name}@${changed.version}`.slice(0, 100),
    failure: `${listed} ${fix}`.slice(0, 300),
    path: changed.path,
    line: changed.line,
    reference: `https://osv.dev/vulnerability/${worst.id}`,
    detail: `The change adds ${changed.name}@${changed.version}, which ${advisories.length === 1 ? "an advisory lists" : "these advisories list"} as affected.`,
  };
}

export async function checkDependencies(options: {
  readonly checkout: string;
  readonly baseSha: string;
  readonly headSha: string;
  readonly files: readonly DiffFile[];
  readonly network: boolean;
  readonly request?: JsonRequest;
}): Promise<DependencyCheck> {
  const packages = await changedPackages(options);
  const report = (status: CommandReport["status"], detail: string): CommandReport => ({ stack: "dependencies", tool: "osv", status, detail, diagnostics: [] });

  if (packages.length === 0) {
    return { hits: [], reports: [] };
  }

  if (!options.network) {
    return { hits: [], reports: [report("skipped", `the network is off, so ${packages.length} changed packages were not checked`)] };
  }

  const advisories = await findAdvisories({ packages, request: options.request ?? osvRequest }).catch((error: unknown) =>
    error instanceof Error ? error : new Error(String(error)),
  );

  if (advisories instanceof Error) {
    return { hits: [], reports: [report("failed", `OSV could not be read: ${advisories.message.slice(0, 200)}`)] };
  }

  const hits = packages.flatMap((changed) => {
    const hit = packageHit({ changed, advisories: advisories.get(packageKey(changed)) ?? [] });

    return hit === null ? [] : [hit];
  });

  return { hits: hits.slice(0, maximumHits), reports: [report("ran", `${packages.length} added or changed packages checked, ${hits.length} with advisories`)] };
}
