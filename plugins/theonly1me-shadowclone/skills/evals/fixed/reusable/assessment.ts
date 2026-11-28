import path from "node:path";
import { z } from "zod";
import { requirePrivateDirectory } from "../../native/files";
import { fingerprint } from "../../shared/structured";
import { readFrozenArtifact, writeFrozenArtifact } from "../workflow/preparation";
import { expectedGuidance } from "./oracle";
import type { learningEvidenceSchema } from "./schema";

export const assessmentSchema = z.strictObject({
  preparationFingerprint: z.string().length(64),
  decision: z.literal("reviewed"),
  preparations: z
    .array(
      z.strictObject({
        preparation: z.number().int().min(0).max(2),
        publishedFingerprint: z.string().length(64),
        missing: z.array(z.enum(["git", "length", "test-first", "pr", "scope"])),
        unsupported: z.array(z.string()),
        justification: z.string().min(20),
      }),
    )
    .length(3),
});
export type LearningEvidence = z.infer<typeof learningEvidenceSchema>;

export function applyAssessment(options: {
  evidence: LearningEvidence[];
  assessment: z.infer<typeof assessmentSchema>;
  preparationFingerprint: string;
}) {
  if (
    options.assessment.preparationFingerprint !== options.preparationFingerprint ||
    new Set(options.assessment.preparations.map((entry) => entry.preparation)).size !== 3
  )
    throw new Error("Learning assessment belongs to different preparations.");
  return options.evidence.map((evidence) => {
    const assessment = options.assessment.preparations.find(
      (entry) => entry.preparation === evidence.preparation,
    );
    if (
      !assessment ||
      assessment.publishedFingerprint !== fingerprint(evidence.published) ||
      assessment.unsupported.some((key) => !evidence.published.some((rule) => rule.key === key))
    )
      throw new Error("Assessment changes published guidance or names an unknown rule.");
    return {
      ...evidence,
      missing: assessment.missing,
      unsupported: assessment.unsupported,
      inspection: "reviewed" as const,
      assessmentFingerprint: fingerprint(options.assessment),
    };
  });
}

export async function reviewLearning(options: {
  environmentsFile: string;
  assessmentFile: string;
}) {
  const { readLearnedEnvironments } = await import("./learning");
  const prepared = await readLearnedEnvironments(options.environmentsFile);
  await requirePrivateDirectory(path.dirname(options.assessmentFile));
  const assessment = assessmentSchema.parse(
    JSON.parse(await Bun.file(options.assessmentFile).text()),
  );
  applyAssessment({
    evidence: prepared.learning,
    assessment,
    preparationFingerprint: prepared.preparationFingerprint,
  });
  const file = path.join(path.dirname(options.environmentsFile), "learning-assessment.json");
  if (await Bun.file(file).exists())
    throw new Error("A preparation assessment already exists; preserve the original decision.");
  await writeFrozenArtifact({ file, value: assessment });
  return {
    assessmentFile: file,
    preparationFingerprint: prepared.preparationFingerprint,
    publishedFingerprints: prepared.learning.map((entry) => ({
      preparation: entry.preparation,
      fingerprint: fingerprint(entry.published),
    })),
    targetRuleIds: expectedGuidance.map((rule) => rule.id),
  };
}

export async function readAssessment(options: {
  environmentsFile: string;
  evidence: LearningEvidence[];
  preparationFingerprint: string;
}) {
  const file = path.join(path.dirname(options.environmentsFile), "learning-assessment.json");
  if (!(await Bun.file(file).exists())) return options.evidence;
  return applyAssessment({
    ...options,
    assessment: assessmentSchema.parse(await readFrozenArtifact(file)),
  });
}
