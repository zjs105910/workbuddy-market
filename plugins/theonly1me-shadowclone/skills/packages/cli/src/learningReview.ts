import { z } from "zod";
import { sourceIds, projectPaths } from "@shadowclone/core";
import { redactSecrets } from "@shadowclone/redact";
import { applyPreferencePreview, previewPreferenceEdit, previewSourceRemoval, type PreferencePreview } from "@shadowclone/learning";

function printablePreview(preview: PreferencePreview) {
  return {
    fingerprint: preview.fingerprint,
    pendingRulesToReject: preview.rejectedPendingKeys ?? [],
    changes: preview.changes.map(({ before, after }) => ({
      key: after.rule.key,
      before: { scope: before.rule.scope, guidance: redactSecrets({ text: before.rule.body }) },
      after: {
        scope: after.rule.scope,
        repository: after.rule.repositoryName,
        guidance: redactSecrets({ text: after.rule.body }),
        retired: after.retirementRequested === true,
      },
    })),
  };
}

export async function handleLearningReview(arguments_: readonly string[]): Promise<boolean> {
  const [action, key, ...rest] = arguments_;
  if (action !== "retire" && action !== "replace" && action !== "narrow" && action !== "remove-source") return false;
  if (!key) throw new Error("Choose a learned rule key or capture source");
  const apply = rest.includes("--apply");
  const expectedPosition = rest.indexOf("--expected");
  const expected = expectedPosition === -1 ? undefined : rest[expectedPosition + 1];
  if (expectedPosition !== -1 && (!expected || !/^[a-f0-9]{64}$/u.test(expected))) {
    throw new Error("--expected needs the fingerprint from the reviewed preview");
  }
  const words = rest.filter((word, index) => word !== "--apply" && word !== "--expected" &&
    (expectedPosition === -1 || index !== expectedPosition + 1));
  if (words.some((word) => word.startsWith("--")) || (action !== "replace" && words.length > 0)) {
    throw new Error("Use learning retire|narrow <key>, replace <key> <guidance>, or remove-source <source>, with optional --apply and --expected <fingerprint>");
  }

  let preview: PreferencePreview;
  if (action === "remove-source") {
    const source = z.enum(sourceIds).parse(key);
    const removal = await previewSourceRemoval({ paths: projectPaths, source });
    preview = removal.preview;
    console.log(JSON.stringify({
      source,
      mixedSourceRulesPreserved: removal.mixed,
      unresolvedProvenancePreserved: removal.unresolved,
      ...printablePreview(preview),
    }, null, 2));
  } else {
    preview = await previewPreferenceEdit({
      paths: projectPaths,
      edit: { kind: action, key, text: words.join(" ") },
      cwd: process.cwd(),
    });
    console.log(JSON.stringify(printablePreview(preview), null, 2));
  }
  if (expected !== undefined && expected !== preview.fingerprint) {
    throw new Error("Learning changed since the reviewed preview. Review the new change before applying it.");
  }
  if (apply && (preview.changes.length > 0 || (preview.rejectedPendingKeys?.length ?? 0) > 0)) {
    const result = await applyPreferencePreview({ paths: projectPaths, preview });
    console.log(`Recorded revision ${result.revision ?? "unchanged"}; ${result.applied} skill change(s) published, ${result.pending} delivery decision(s) pending. Use learning pending to inspect blockers or history and undo to reverse a revision.`);
  } else if (!apply) {
    console.log("Preview only. Add --apply --expected with this fingerprint after reviewing the change.");
  }
  return true;
}
