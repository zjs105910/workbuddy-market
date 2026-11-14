import { expect, test } from "bun:test";
import { deriveSignals } from "@shadowclone/sessions";
import { renderMirror } from "./mirror";

test("steering episode counts are not ratios against unrelated interruption markers", async () => {
  const derived = await deriveSignals({
    events: [],
    corpus: { sessions: 0, bytes: 0, activeDays: 0 },
    gitMetadataEnabled: false,
  });
  const output = renderMirror({
    report: derived.report,
    deepLearningPreview: { eligibleSteeringEpisodes: 10, extractionBatches: 1 },
  });
  const line = output
    .split("\n")
    .find((entry) => entry.includes("eligible user steering episodes"));

  expect(line).toContain("10");
  expect(line).not.toContain("of 0");
  expect(output).toContain("Interaction markers found");
});

test("reports metadata-only profile updates without claiming the profile was unchanged", async () => {
  const derived = await deriveSignals({
    events: [],
    corpus: { sessions: 0, bytes: 0, activeDays: 0 },
    gitMetadataEnabled: false,
  });

  const output = renderMirror({
    report: derived.report,
    deepLearningPreview: {
      eligibleSteeringEpisodes: 1,
      extractionBatches: 1,
    },
    deepChangesProposed: 0,
    profileUpdated: true,
  });

  expect(output).toContain("existing guidance was updated.");
  expect(output).not.toContain("Profile unchanged.");
});
