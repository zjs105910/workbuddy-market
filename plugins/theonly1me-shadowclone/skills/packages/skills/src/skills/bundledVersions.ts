import { z } from "zod";
import recorded from "./bundledVersions.json";

export const bundledVersionsSchema = z.record(
  z.string(),
  z.record(z.string(), z.array(z.string().regex(/^[0-9a-f]{64}$/))),
);

export type BundledVersions = z.infer<typeof bundledVersionsSchema>;

export function bundledVersionIndex(
  versions: BundledVersions,
): ReadonlyMap<string, ReadonlySet<string>> {
  return new Map(
    Object.entries(versions).flatMap(([skill, files]) =>
      Object.entries(files).map(([file, fingerprints]) => [
        `${skill}/${file}`,
        new Set(fingerprints),
      ]),
    ),
  );
}

const index = bundledVersionIndex(bundledVersionsSchema.parse(recorded));

export function isBundledVersion(options: {
  readonly skill: string;
  readonly file: string;
  readonly fingerprint: string;
}): boolean {
  return index.get(`${options.skill}/${options.file}`)?.has(options.fingerprint) ?? false;
}
