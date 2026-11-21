import { expect, test } from "bun:test";
import {
  applyManagedPolicy,
  defaultConfig,
  defaultManagedPolicy,
  parseManagedPolicy,
} from "./index";

test("managed policy can only narrow user source consent", () => {
  const config = {
    ...defaultConfig,
    sources: {
      "agent-context": true,
      antigravity: true,
      "antigravity-workspaces": true,
      "claude-memory": true,
      "claude-rules": true,
      "claude-code": true,
      "claude-prompts": true,
      codex: false,
      cursor: false,
      pi: true,
      "declared-rules": true,
      "git-metadata": true,
      "repository-manifests": true,
      "github-writing": true,
      "skill-library": true,
    },
    distillation: { deep: true },
  };

  const policy = {
    ...defaultManagedPolicy,
    allowedSources: ["claude-code"] as const,
    distillation: "disabled" as const,
  };

  const effective = applyManagedPolicy({ config, policy });

  expect(effective.sources["claude-code"]).toBeTrue();
  expect(effective.sources.antigravity).toBeFalse();
  expect(effective.sources["claude-prompts"]).toBeFalse();
  expect(effective.sources["declared-rules"]).toBeFalse();
  expect(effective.sources["claude-rules"]).toBeFalse();
  expect(effective.sources["git-metadata"]).toBeFalse();
  expect(effective.sources["github-writing"]).toBeFalse();
  expect(effective.sources["repository-manifests"]).toBeFalse();
  expect(effective.distillation.deep).toBeFalse();
});

test("a disabled managed policy is a hard stop", () => {
  const config = {
    ...defaultConfig,
    sources: { ...defaultConfig.sources, "claude-code": true },
    distillation: { deep: true },
  };
  const effective = applyManagedPolicy({
    config,
    policy: { ...defaultManagedPolicy, enabled: false },
  });

  expect(
    Object.values(effective.sources).every((enabled) => !enabled),
  ).toBeTrue();
  expect(effective.distillation.deep).toBeFalse();
});

test("rejects unknown engines in managed policy", () => {
  expect(() =>
    parseManagedPolicy({
      enabled: true,
      allowedSources: ["claude-code"],
      allowedEngines: ["unknown"],
      distillation: "allowed",
      originScope: "strict",
      blockedOrigins: [],
      maxActionTier: "draft",
    }),
  ).toThrow("invalid or missing fields");
});

test("drops the retired shell source from managed policy and still rejects unknown sources", () => {
  const policy = {
    enabled: true,
    allowedEngines: ["claude-code"],
    distillation: "allowed",
    originScope: "strict",
    blockedOrigins: [],
    maxActionTier: "draft",
  };

  expect(
    parseManagedPolicy({ ...policy, allowedSources: ["claude-code", "shell"] })
      .allowedSources,
  ).toEqual(["claude-code"]);
  expect(() =>
    parseManagedPolicy({ ...policy, allowedSources: ["invented"] }),
  ).toThrow("invalid or missing fields");
});

test("managed policy retains harness and model selections while narrowing learning permissions", () => {
  for (const engine of ["claude-code", "codex", "cursor-agent", "pi"] as const) {
    const preferences = { deep: true, automatic: true, engine, model: "synthetic-model" };
    const config = { ...defaultConfig, distillation: preferences };
    expect(applyManagedPolicy({ config, policy: defaultManagedPolicy }).distillation).toEqual(preferences);
    const restricted = applyManagedPolicy({ config, policy: {
      ...defaultManagedPolicy, allowedEngines: [], distillation: "disabled",
    } });
    expect(restricted.distillation).toEqual({ ...preferences, deep: false, automatic: false });
  }
});
