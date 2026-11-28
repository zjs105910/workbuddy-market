import { expect, test } from "bun:test";
import { skillClassification } from "./classification";

test("reads nested portable skill classification", () => {
  const document = [
    "---",
    "name: synthetic-skill",
    "description: Synthetic guidance.",
    "metadata:",
    "  shadowclone-category: testing",
    "  shadowclone-section: workflow",
    "  shadowclone-axis: testing-approach",
    "  shadowclone-applies-when: changing observable behavior",
    "---",
    "Synthetic instructions.",
  ].join("\n");

  expect(skillClassification(document)).toEqual({
    appliesWhen: "changing observable behavior",
    category: "testing",
    section: "workflow",
    axis: "testing-approach",
  });
});
