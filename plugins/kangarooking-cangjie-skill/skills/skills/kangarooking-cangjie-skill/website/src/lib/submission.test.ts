import { describe, expect, it } from "vitest";
import { createRegistryEntry, serializeRegistryEntry, slugify, validateSkillFolder } from "./submission";

describe("submission helpers", () => {
  it("creates a schema-shaped GitHub entry", () => {
    const entry = createRegistryEntry({
      mode: "github",
      name: "Decision Skill",
      slug: "decision-skill",
      summary: "一套用于检查复杂决策假设的工作方法。",
      repositoryUrl: "https://github.com/example/decision-skill.git",
      skillCount: 3,
      domains: "决策，管理",
      languages: ["zh-CN"],
      useCases: "检查决策假设\n复盘行动结果",
    });
    expect(entry.source_url).toBe("https://github.com/example/decision-skill");
    expect(entry.domains).toEqual(["决策", "管理"]);
    expect(serializeRegistryEntry(entry)).toContain("schema_version: 1");
  });

  it("validates local folders and counts SKILL.md files", () => {
    const result = validateSkillFolder([
      { name: "README.md", size: 100, webkitRelativePath: "my-pack/README.md" },
      { name: "SKILL.md", size: 200, webkitRelativePath: "my-pack/a/SKILL.md" },
      { name: "SKILL.md", size: 200, webkitRelativePath: "my-pack/b/SKILL.md" },
      { name: ".DS_Store", size: 10, webkitRelativePath: "my-pack/.DS_Store" },
    ]);
    expect(result.valid).toBe(true);
    expect(result.skillCount).toBe(2);
    expect(result.acceptedFiles).toHaveLength(3);
  });

  it("rejects likely secrets and invalid slugs", () => {
    expect(validateSkillFolder([{ name: ".env", size: 10, webkitRelativePath: "pack/.env" }]).valid).toBe(false);
    expect(slugify("My Great Skill")).toBe("my-great-skill");
    expect(() => createRegistryEntry({
      mode: "bundled",
      name: "测试",
      slug: "不合法",
      summary: "这是一个足够长的测试描述文本。",
      skillCount: 1,
      domains: "测试",
      languages: ["zh-CN"],
      useCases: "完成一个测试任务",
    })).toThrow(/Slug/);
  });
});
