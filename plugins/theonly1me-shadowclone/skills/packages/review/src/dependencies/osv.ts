import { z } from "zod";
import type { Finding } from "../types";
import { type LockedPackage, packageKey } from "./types";

export type JsonRequest = (options: { readonly url: string; readonly body?: unknown }) => Promise<unknown>;

export type Advisory = {
  readonly id: string;
  readonly summary: string;
  readonly severity: Finding["severity"];
  readonly fixedVersions: readonly string[];
};

const batchSize = 500;
const maximumAdvisories = 30;

export const osvRequest: JsonRequest = async (options) => {
  const response = await fetch(options.url, {
    method: options.body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    signal: AbortSignal.timeout(20_000),
  });

  if (!response.ok) {
    throw new Error(`OSV returned ${response.status}`);
  }

  return response.json();
};

const batchSchema = z.object({
  results: z.array(z.object({ vulns: z.array(z.object({ id: z.string().regex(/^[\w.:-]+$/) })).optional() })),
});

const vulnerabilitySchema = z.object({
  id: z.string(),
  summary: z.string().optional(),
  details: z.string().optional(),
  database_specific: z.object({ severity: z.string().optional() }).optional(),
  affected: z
    .array(
      z.object({
        package: z.object({ name: z.string(), ecosystem: z.string() }).optional(),
        ranges: z.array(z.object({ events: z.array(z.record(z.string(), z.string())) })).optional(),
      }),
    )
    .optional(),
});

type Vulnerability = z.infer<typeof vulnerabilitySchema>;

function severityOf(vulnerability: Vulnerability): Finding["severity"] {
  const label = (vulnerability.database_specific?.severity ?? "").toUpperCase();

  if (label === "CRITICAL" || label === "HIGH") {
    return "high";
  }

  return label === "LOW" ? "low" : "medium";
}

function advisoryFor(options: { readonly vulnerability: Vulnerability; readonly lockedPackage: LockedPackage }): Advisory {
  const { vulnerability, lockedPackage } = options;
  const fixedVersions = (vulnerability.affected ?? [])
    .filter((entry) => entry.package?.name === lockedPackage.name && entry.package.ecosystem === lockedPackage.ecosystem)
    .flatMap((entry) => (entry.ranges ?? []).flatMap((range) => range.events.flatMap((event) => (event.fixed ? [event.fixed] : []))));
  const summary = (vulnerability.summary ?? vulnerability.details ?? "No summary is published.").split("\n")[0] ?? "";

  return { id: vulnerability.id, summary: summary.slice(0, 200), severity: severityOf(vulnerability), fixedVersions: [...new Set(fixedVersions)] };
}

export async function findAdvisories(options: {
  readonly packages: readonly LockedPackage[];
  readonly request: JsonRequest;
}): Promise<ReadonlyMap<string, readonly Advisory[]>> {
  const idsByPackage = new Map<string, readonly string[]>();

  for (let start = 0; start < options.packages.length; start += batchSize) {
    const batch = options.packages.slice(start, start + batchSize);
    const answer = batchSchema.parse(
      await options.request({
        url: "https://api.osv.dev/v1/querybatch",
        body: { queries: batch.map((entry) => ({ package: { name: entry.name, ecosystem: entry.ecosystem }, version: entry.version })) },
      }),
    );

    batch.forEach((entry, index) => {
      const ids = (answer.results[index]?.vulns ?? []).map((vulnerability) => vulnerability.id);

      if (ids.length > 0) {
        idsByPackage.set(packageKey(entry), ids);
      }
    });
  }

  const ids = [...new Set([...idsByPackage.values()].flat())].slice(0, maximumAdvisories);
  const vulnerabilities = new Map(
    await Promise.all(
      ids.map(async (id) => [id, vulnerabilitySchema.parse(await options.request({ url: `https://api.osv.dev/v1/vulns/${id}` }))] as const),
    ),
  );

  return new Map(
    options.packages.flatMap((lockedPackage) => {
      const advisories = (idsByPackage.get(packageKey(lockedPackage)) ?? []).flatMap((id) => {
        const vulnerability = vulnerabilities.get(id);

        return vulnerability ? [advisoryFor({ vulnerability, lockedPackage })] : [];
      });

      return advisories.length > 0 ? [[packageKey(lockedPackage), advisories] as const] : [];
    }),
  );
}
