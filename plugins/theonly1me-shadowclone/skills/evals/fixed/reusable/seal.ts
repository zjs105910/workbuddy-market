import path from "node:path";
import { readBoundedFile } from "@shadowclone/core";
import { requirePrivateDirectory } from "../../native/files";
import { fingerprint } from "../../shared/structured";
import { readFrozenArtifact, writeFrozenArtifact } from "../workflow/preparation";
import { developmentCases, benchmarkFingerprint } from "./definition";
import manifest from "./heldout-manifest.json";
import { bundleSchema, families, publishedBundleSchema, reviewSchema } from "./schema";
import { graderFingerprint } from "./identity";
import { validateGraders } from "./validation";

export const publishedHeldout = publishedBundleSchema.parse(manifest);
export async function readHeldout(file: string) {
  const root = await requirePrivateDirectory(path.dirname(file));
  const text = await readBoundedFile({
    filePath: path.join(root, path.basename(file)),
    roots: [root],
    maximumBytes: 2_000_000,
  });
  if (text === null) throw new Error("Private held-out bundle is unavailable.");
  const bundle = bundleSchema.parse(JSON.parse(text));
  if (fingerprint(bundle) !== publishedHeldout.fingerprint)
    throw new Error("Held-out bundle does not match published seal.");
  for (const entry of bundle.cases) {
    const expected = publishedHeldout.cases.find((item) => item.id === entry.task.id);
    if (
      entry.split !== "held-out" ||
      !expected ||
      expected.family !== entry.family ||
      fingerprint(entry) !== expected.fingerprint
    )
      throw new Error("Held-out case seal differs.");
  }
  if (new Set(bundle.cases.map((entry) => entry.family)).size !== families.length)
    throw new Error("Held-out family coverage differs.");
  return bundle;
}

export async function writeCaseReview(options: { bundleFile: string; reviewFile: string }) {
  const bundle = await readHeldout(options.bundleFile);
  const allCases = [...developmentCases, ...bundle.cases];
  const calibration = validateGraders(allCases);
  if (!calibration.passed) throw new Error("Case calibration failed before review.");
  const reviewFingerprint = fingerprint({
    benchmarkFingerprint,
    heldout: publishedHeldout,
    grader: await graderFingerprint(),
    calibration,
  });
  const review = reviewSchema.parse({
    fingerprint: reviewFingerprint,
    decision: "draft",
    calibrationFingerprint: fingerprint(calibration),
    cases: allCases.map((entry) => ({
      id: entry.task.id,
      family: entry.family,
      split: entry.split,
      specification: entry.specification,
      checks: [
        ...entry.task.checks.map((check) => check.kind),
        ...entry.extraChecks.map((check) => check.kind),
      ],
    })),
  });
  await requirePrivateDirectory(path.dirname(options.reviewFile));
  if (await Bun.file(options.reviewFile).exists())
    throw new Error("Case review already exists; preserve the original review.");
  await writeFrozenArtifact({ file: options.reviewFile, value: review });
  return {
    reviewFile: options.reviewFile,
    fingerprint: reviewFingerprint,
    decision: review.decision,
    cases: review.cases.length,
    calibration,
  };
}

export async function approveCaseReview(options: { reviewFile: string; fingerprint: string }) {
  const review = reviewSchema.parse(await readFrozenArtifact(options.reviewFile));
  if (review.fingerprint !== options.fingerprint || review.decision !== "draft")
    throw new Error("Review decision must match the current draft fingerprint.");
  await writeFrozenArtifact({
    file: options.reviewFile,
    value: { ...review, decision: "approved" },
  });
  return { reviewFile: options.reviewFile, fingerprint: review.fingerprint, decision: "approved" };
}

export async function requireCaseReview(options: { reviewFile: string; bundleFile: string }) {
  const review = reviewSchema.parse(await readFrozenArtifact(options.reviewFile));
  const bundle = await readHeldout(options.bundleFile);
  const calibration = validateGraders([...developmentCases, ...bundle.cases]);
  const current = fingerprint({
    benchmarkFingerprint,
    heldout: publishedHeldout,
    grader: await graderFingerprint(),
    calibration,
  });
  if (review.decision !== "approved" || review.fingerprint !== current)
    throw new Error("Freezing requires an approved current case-and-verdict review.");
  return review;
}
