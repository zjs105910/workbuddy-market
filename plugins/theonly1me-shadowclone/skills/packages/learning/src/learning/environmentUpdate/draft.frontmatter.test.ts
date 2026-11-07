import { expect, test } from "bun:test";
import { parseSkillDocument } from "@shadowclone/skills";
import { applySkillDraft } from "./draft";
import { learningRecord } from "@shadowclone/environment/testing";

const record = learningRecord();
const body = "\n# Palette checks\n\nReject duplicate colors.\n\n---\n\nKeep the palette order.\n";
const document = `---\nname: palette-check\ndescription: Validate palettes\n---\n${body}`;
const options = {
  original: null,
  name: "palette-check",
  description: "Validate palettes",
  records: [record],
  draft: {
    outcomes: [{ key: record.rule.key, disposition: "apply" as const, reason: "Supported" }],
    description: "Validate palettes before writing them",
    edits: [],
    body: document,
  },
};

test("a complete generated document receives one metadata block and preserves its body", () => {
  const result = applySkillDraft(options);
  const parsed = parseSkillDocument(result);

  expect(parsed.body).toBe(body);
  expect(parsed.metadata).toEqual({
    name: "palette-check",
    description: options.draft.description,
  });
  expect(applySkillDraft({
    ...options,
    original: result,
    draft: { ...options.draft, body: "" },
  })).toBe(result);
});

test("ambiguous generated metadata cannot become skill body text", () => {
  for (const generated of [
    document.replace("palette-check", "unrelated-workflow"),
    document.replace("name: palette-check", "name: palette-check\nname: another"),
    `---\nname: palette-check\n${body}`,
    document.replace(body, document),
  ]) {
    expect(() => applySkillDraft({
      ...options,
      draft: { ...options.draft, body: generated },
    })).toThrow();
  }
});

test("ordinary Markdown and fenced frontmatter examples remain intact", () => {
  const plain = `# Palette checks\n\n\`\`\`yaml\n${document}\`\`\`\n`;
  const result = applySkillDraft({ ...options, draft: { ...options.draft, body: plain } });

  expect(parseSkillDocument(result).body).toBe(plain);
});
