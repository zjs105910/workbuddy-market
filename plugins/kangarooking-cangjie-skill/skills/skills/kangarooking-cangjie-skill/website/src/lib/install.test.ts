import { describe, expect, it } from "vitest";
import type { RegistryEntry } from "./catalog";
import { getAgentInstallPrompt, INSTALL_GUIDE_URL } from "./install";

const baseEntry: RegistryEntry = {
  schema_version: 1,
  slug: "example-skill",
  name: "Example Skill",
  summary: "A sufficiently descriptive example skill summary.",
  source_type: "github",
  source_url: "https://github.com/example/example-skill",
  skill_count: 1,
  domains: ["测试"],
  language: ["zh-CN"],
  status: "active",
  quality: "community",
  use_cases: ["完成一个测试任务"],
};

describe("Agent install prompt", () => {
  it("generates a copy-ready prompt for GitHub skills", () => {
    expect(getAgentInstallPrompt(baseEntry)).toBe(
      `请根据 ${INSTALL_GUIDE_URL}，从 https://github.com/example/example-skill 安装 example-skill。安装后新增 1 个 Skill。`,
    );
  });

  it("mentions the single entrypoint and capability cards for v2 single packs", () => {
    const prompt = getAgentInstallPrompt({
      ...baseEntry,
      schema_version: 2,
      output_mode: "single",
      entrypoint_count: 1,
      capability_count: 19,
    });
    expect(prompt).toContain("single 模式");
    expect(prompt).toContain("19 张");
  });

  it("mentions the router entrypoint for v2 compact packs", () => {
    const prompt = getAgentInstallPrompt({
      ...baseEntry,
      schema_version: 2,
      output_mode: "pack",
      skill_count: 7,
      entrypoint_count: 7,
      capability_count: 19,
      router_entrypoint: "naval-almanack",
    });
    expect(prompt).toContain("compact pack");
    expect(prompt).toContain("7 个 Skill 入口");
    expect(prompt).toContain("naval-almanack");
  });

  it("includes the exact bundled path when the skill lives in this repository", () => {
    expect(getAgentInstallPrompt({
      ...baseEntry,
      source_type: "bundled",
      source_url: "https://github.com/kangarooking/cangjie-skill",
      skill_path: "registry/example-skill/skill",
    })).toContain("registry/example-skill/skill");
  });

  it("can use the local guide while the site is in development", () => {
    expect(getAgentInstallPrompt(baseEntry, "http://localhost:4321/install/cangjie-skill.md"))
      .toContain("http://localhost:4321/install/cangjie-skill.md");
  });
});
