import { fileSchema } from "../../native/schema";
import { taskSchema, type StudyTask } from "../../native/study/schema";

const file = (options: { path: string; content: string }) => fileSchema.parse(options);

function codeTask(options: {
  id: string; request: string; initial: string; reference: string; assertions: string; turns?: string[]; commentsAllowed?: boolean;
}): StudyTask {
  const source = file({ path: "src/subject.ts", content: options.initial });
  return taskSchema.parse({
    id: options.id, mode: "code", turns: [options.request, ...(options.turns ?? [])], fixtures: [],
    git: { checkout: "work", pushed: false, branches: [{ name: "work", commits: [{ message: "chore: initialize fixture", files: [source] }] }] },
    acceptance: {
      files: [file({ path: "acceptance.test.ts", content: `import { expect, test } from "bun:test";\nimport * as subject from "./src/subject";\ntest("acceptance", async () => {\n${options.assertions}\n});\n` })],
      commands: [{ arguments: ["bun", "test", "acceptance.test.ts"] }],
      reference: [file({ path: "src/subject.ts", content: options.reference })],
    },
    checks: [
      ...(options.commentsAllowed ? [] : [{ id: "comments", keyItem: "comments", kind: "no-added-comments" }]),
      { id: "types", keyItem: "types", kind: "no-unsafe-types" },
      ...(options.id === "new-api" ? [{ id: "parameters", keyItem: "parameters", kind: "options-object" }] : []),
      { id: "git", keyItem: "git", kind: "no-git-writes" },
      { id: "brevity", keyItem: "brevity", kind: "max-words", turn: options.turns?.length ?? 0, maximum: 80 },
    ],
  });
}

export const tasks: StudyTask[] = [
  codeTask({
    id: "new-api",
    request: "Add an exported formatInterval function to src/subject.ts. It accepts start and end numbers and returns them separated by '..', such as '2..5'. Choose its API. Negative bounds and equal bounds are valid. Add tests.",
    initial: "export {};\n",
    reference: "export function formatInterval(options: { start: number; end: number }): string {\n  return String(options.start) + '..' + String(options.end);\n}\n",
    assertions: "const format = (start: number, end: number) => Reflect.apply(subject.formatInterval, null, subject.formatInterval.length >= 2 ? [start, end] : [{ start, end }]);\nexpect(format(2, 5)).toBe('2..5');\nexpect(format(-3, -1)).toBe('-3..-1');\nexpect(format(0, 0)).toBe('0..0');",
  }),
  codeTask({
    id: "discount-total",
    request: "Fix calculateTotal in src/subject.ts. It should apply the percentage discount to unitPrice times quantity and round the result to cents. Keep the public API compatible. Cover zero quantity, no discount, full discount, and fractional cents.",
    initial: "export function calculateTotal(options: { unitPrice: number; quantity: number; discountPercent: number }): number {\n  return options.unitPrice * options.quantity;\n}\n",
    reference: "export function calculateTotal(options: { unitPrice: number; quantity: number; discountPercent: number }): number {\n  return Math.round(options.unitPrice * options.quantity * (1 - options.discountPercent / 100) * 100) / 100;\n}\n",
    assertions: "expect(subject.calculateTotal({ unitPrice: 10, quantity: 2, discountPercent: 25 })).toBe(15);\nexpect(subject.calculateTotal({ unitPrice: 1, quantity: 0, discountPercent: 0 })).toBe(0);\nexpect(subject.calculateTotal({ unitPrice: 1.235, quantity: 1, discountPercent: 0 })).toBe(1.24);\nexpect(subject.calculateTotal({ unitPrice: 10, quantity: 2, discountPercent: 100 })).toBe(0);",
  }),
  codeTask({
    id: "duration-extension",
    request: "Extend parseDuration in src/subject.ts to support integer minutes such as '3m' as well as seconds such as '2s'. Return seconds. Invalid input returns null, including negative values and missing units.",
    turns: ["Also support integer hours such as '2h'. Keep seconds and minutes working, and reject fractional amounts."],
    initial: "export function parseDuration(input: string): number | null {\n  const match = /^(\\d+)s$/.exec(input);\n  return match?.[1] ? Number(match[1]) : null;\n}\n",
    reference: "export function parseDuration(input: string): number | null {\n  const match = /^(\\d+)([smh])$/.exec(input);\n  if (!match?.[1] || !match[2]) return null;\n  const multiplier = match[2] === 'h' ? 3600 : match[2] === 'm' ? 60 : 1;\n  return Number(match[1]) * multiplier;\n}\n",
    assertions: "expect(subject.parseDuration('2s')).toBe(2);\nexpect(subject.parseDuration('3m')).toBe(180);\nexpect(subject.parseDuration('2h')).toBe(7200);\nfor (const input of ['-1m', '2.5h', '4', '2d', '']) expect(subject.parseDuration(input)).toBeNull();",
  }),
  codeTask({
    id: "deduplicate-labels",
    request: "Implement uniqueLabels in src/subject.ts. Trim each label, discard empty labels, deduplicate without regard to case, and keep the first label's spelling and original order. Do not mutate the input.",
    initial: "export function uniqueLabels(labels: readonly string[]): string[] {\n  return [...labels];\n}\n",
    reference: "export function uniqueLabels(labels: readonly string[]): string[] {\n  const seen = new Set<string>();\n  return labels.map((label) => label.trim()).filter((label) => {\n    const key = label.toLowerCase();\n    if (!label || seen.has(key)) return false;\n    seen.add(key);\n    return true;\n  });\n}\n",
    assertions: "const labels = [' Alpha ', 'alpha', '', 'BETA', ' beta ', 'Gamma'];\nexpect(subject.uniqueLabels(labels)).toEqual(['Alpha', 'BETA', 'Gamma']);\nexpect(labels[0]).toBe(' Alpha ');\nexpect(subject.uniqueLabels([])).toEqual([]);",
  }),
  codeTask({
    id: "immutable-sort",
    request: "Fix sortScores in src/subject.ts to return scores in descending numeric order while preserving its input. Empty input should return a fresh empty array.",
    initial: "export function sortScores(scores: number[]): number[] {\n  return scores.sort();\n}\n",
    reference: "export function sortScores(scores: number[]): number[] {\n  return [...scores].sort((left, right) => right - left);\n}\n",
    assertions: "const scores = [2, 10, 1];\nexpect(subject.sortScores(scores)).toEqual([10, 2, 1]);\nexpect(scores).toEqual([2, 10, 1]);\nconst empty: number[] = [];\nexpect(subject.sortScores(empty)).toEqual([]);\nexpect(subject.sortScores(empty)).not.toBe(empty);",
  }),
  codeTask({
    id: "explicit-comment-override",
    request: "Implement clamp in src/subject.ts, clamping value to the inclusive minimum and maximum. For this task, explicitly add the single code comment '// Inclusive bounds.' immediately above the exported function. Keep the existing public API.",
    commentsAllowed: true,
    initial: "export function clamp(options: { value: number; minimum: number; maximum: number }): number {\n  return options.value;\n}\n",
    reference: "// Inclusive bounds.\nexport function clamp(options: { value: number; minimum: number; maximum: number }): number {\n  return Math.min(options.maximum, Math.max(options.minimum, options.value));\n}\n",
    assertions: "expect(subject.clamp({ value: -1, minimum: 0, maximum: 10 })).toBe(0);\nexpect(subject.clamp({ value: 20, minimum: 0, maximum: 10 })).toBe(10);\nexpect(subject.clamp({ value: 5, minimum: 0, maximum: 10 })).toBe(5);\nexpect(await Bun.file('src/subject.ts').text()).toContain('// Inclusive bounds.\\nexport function clamp');",
  }),
  taskSchema.parse({
    id: "concise-advice", mode: "advice", git: null, fixtures: [], acceptance: null,
    turns: ["Explain why JavaScript's default array sort puts 10 before 2, and show the comparator for ascending numeric order. Mention both string conversion and the comparator."],
    checks: [{ id: "brevity", keyItem: "brevity", kind: "max-words", turn: 0, maximum: 80 },
      { id: "content", keyItem: "brevity", kind: "patterns", turn: 0, extract: "all", required: ["string", "\\b(?:a|left)\\s*-\\s*(?:b|right)\\b"], forbidden: [] }],
  }),
];
