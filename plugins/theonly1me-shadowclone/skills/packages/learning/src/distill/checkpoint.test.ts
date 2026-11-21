import { expect, test } from "bun:test";
import { checkpointId } from "./checkpoint";

test("binds reconciliation checkpoints to prompt, schema, and learner version", () => {
  const baseline = checkpointId({
    prompt: "prompt-one",
    outputSchema: { type: "object" },
    learnerVersion: "learner-one",
  });

  expect(
    checkpointId({
      prompt: "prompt-two",
      outputSchema: { type: "object" },
      learnerVersion: "learner-one",
    }),
  ).not.toBe(baseline);
  expect(
    checkpointId({
      prompt: "prompt-one",
      outputSchema: { type: "array" },
      learnerVersion: "learner-one",
    }),
  ).not.toBe(baseline);
  expect(
    checkpointId({
      prompt: "prompt-one",
      outputSchema: { type: "object" },
      learnerVersion: "learner-two",
    }),
  ).not.toBe(baseline);
});
