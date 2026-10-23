import { expect, test } from "bun:test";
import {
  defaultLearningExecutionLimits,
  learningExecutionLimitsForCalls,
} from "@shadowclone/agents";
import { parseLearnOptions } from "./learnOptions";

test("parses deep review modes", () => {
  expect(parseLearnOptions(["--deep", "--dry-run"])).toEqual({
    deep: true,
    dryRun: true,
    apply: false,
  });
  expect(parseLearnOptions(["--deep", "--apply"])).toEqual({
    deep: true,
    dryRun: false,
    apply: true,
  });
  expect(
    parseLearnOptions([
      "--deep",
      "--engine",
      "codex",
      "--model",
      "gpt-5.6-luna",
      "--reasoning-effort",
      "medium",
    ]),
  ).toEqual({
    deep: true,
    dryRun: false,
    apply: false,
    engine: "codex",
    model: "gpt-5.6-luna",
    reasoningEffort: "medium",
  });
});

test("rejects invalid apply combinations before learning", () => {
  expect(() => parseLearnOptions(["--apply"])).toThrow("requires --deep");
  expect(() => parseLearnOptions(["--deep", "--dry-run", "--apply"])).toThrow(
    "cannot be combined",
  );
  expect(parseLearnOptions(["--unknown"])).toBeNull();
  expect(() => parseLearnOptions(["--engine", "codex"])).toThrow(
    "require --deep",
  );
});

test("a catch-up run raises every learning ceiling together", () => {
  expect(parseLearnOptions(["--deep", "--max-calls", "80"])).toMatchObject({
    deep: true,
    maximumCalls: 80,
  });
  expect(learningExecutionLimitsForCalls(80)).toEqual({
    maximumCalls: 80,
    timeoutMilliseconds: defaultLearningExecutionLimits.timeoutMilliseconds * 4,
    maximumCostUsd: defaultLearningExecutionLimits.maximumCostUsd * 4,
  });
  expect(
    learningExecutionLimitsForCalls(
      defaultLearningExecutionLimits.maximumCalls,
    ),
  ).toEqual(defaultLearningExecutionLimits);
});

test("rejects a call ceiling that is not a positive whole number", () => {
  expect(() => parseLearnOptions(["--deep", "--max-calls", "0"])).toThrow(
    "Invalid learning call ceiling",
  );
  expect(() => parseLearnOptions(["--max-calls", "20"])).toThrow(
    "Learning engine options require --deep",
  );
});
