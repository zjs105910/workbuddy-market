import { expect, test } from "bun:test";
import { deriveSignals } from "@shadowclone/sessions";
import { signalCorpus, signalEvents } from "@shadowclone/sessions/testing";
import { renderMirror } from "./mirror";

test("mines correction markers and renders a text-free mirror", async () => {
  const derived = await deriveSignals({
    events: signalEvents,
    corpus: signalCorpus,
    gitMetadataEnabled: true,
    readRemote: (cwd) =>
      Promise.resolve(
        cwd === "/one"
          ? "git@github.com:acme/repo.git"
          : "https://github.com/other/repo.git",
      ),
  });

  const output = renderMirror({
    report: derived.report,
    deepLearningPreview: {
      eligibleSteeringEpisodes: 1,
      extractionBatches: 1,
    },
  });

  expect(derived.report.interruptions[0]?.label).toBe("while using Edit");
  expect(derived.report.originCount).toBe(2);
  expect(derived.report.correctionCounts).toEqual({
    interruptions: 2,
    permissionDenials: 0,
    answeredQuestions: 1,
    resolvedPlans: 0,
  });
  expect(
    derived.corrections.every((signal) =>
      signal.repositoryName?.startsWith("repo--"),
    ),
  ).toBeTrue();
  expect(output).toContain("No network calls were made.");
  expect(output).toContain("while using Edit");
  expect(output).toContain("reconciliation batch");
  expect(output).toContain("Run shadowclone learn --deep");
  expect(output).not.toContain("Profile written");
  expect(output).not.toContain("/one");
});
