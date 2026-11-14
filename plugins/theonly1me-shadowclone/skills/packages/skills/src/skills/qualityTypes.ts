export type SkillRule =
  | "document"
  | "name"
  | "description"
  | "applies-when"
  | "body-length"
  | "sections"
  | "gates"
  | "example"
  | "completion"
  | "host-tools"
  | "references"
  | "voice"
  | "plain-english";

export type SkillFinding = {
  readonly skill: string;
  readonly line: number;
  readonly rule: SkillRule | "repeated-sentence" | "pending-list" | "script";
  readonly message: string;
};

export function finding(options: {
  readonly skill: string;
  readonly line: number;
  readonly rule: SkillRule;
  readonly message: string;
}): SkillFinding {
  return options;
}
