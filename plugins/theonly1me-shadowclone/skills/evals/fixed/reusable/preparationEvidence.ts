import { readEnvironment } from "@shadowclone/environment";
import { readPendingLearning } from "@shadowclone/learning";
import { listSkillProposals } from "@shadowclone/skills";
import type { LearningCall } from "../workflow/schema";
import { reusableLayout } from "./environments";
import { expectedGuidance } from "./oracle";
import { learningEvidenceSchema } from "./schema";

export async function inspectPreparation(options: {
  directory: string;
  preparation: number;
  calls: LearningCall[];
  completed: boolean;
}) {
  const paths = reusableLayout(options.directory).paths(`deep-${options.preparation}`);
  const environment = await readEnvironment(paths);
  const pending = await readPendingLearning(paths);
  const skillProposals = await listSkillProposals(paths);
  const published =
    environment?.records.flatMap((record) => {
      const disposition = environment.dispositions.find((entry) => entry.key === record.rule.key);
      return disposition && ["published", "covered"].includes(disposition.status)
        ? [
            {
              key: record.rule.key,
              text: `${record.rule.title}\n${record.rule.body}`,
              scope: record.rule.scope,
              status: disposition.status,
            },
          ]
        : [];
    }) ?? [];
  const missing = expectedGuidance
    .filter(
      (expected) =>
        !published.some(
          (rule) =>
            new RegExp(expected.recognition, "iu").test(rule.text) &&
            (expected.scope === "global" ? rule.scope === "global" : rule.scope !== "global"),
        ),
    )
    .map((rule) => rule.id);
  const unsupported = published
    .filter(
      (rule) =>
        expectedGuidance.some((expected) => new RegExp(expected.rejected, "iu").test(rule.text)) ||
        /(?:rewrite.*rust|always.*force.push|standing.*tool.result)/iu.test(rule.text) ||
        (rule.scope === "global" && /\bAtlas\b/u.test(rule.text)),
    )
    .map((rule) => rule.key);
  return learningEvidenceSchema.parse({
    preparation: options.preparation,
    calls: options.calls,
    completed: options.completed,
    published,
    missing,
    pending: [
      ...pending.rules.map((rule) => rule.title),
      ...(environment?.records
        .filter(
          (record) =>
            !environment.dispositions.some(
              (entry) => entry.key === record.rule.key && entry.status !== "pending",
            ),
        )
        .map((record) => record.rule.key) ?? []),
      ...skillProposals
        .filter((proposal) => proposal.status === "pending")
        .map((proposal) => proposal.id),
    ],
    unsupported,
    inspection: "review-required",
  });
}
