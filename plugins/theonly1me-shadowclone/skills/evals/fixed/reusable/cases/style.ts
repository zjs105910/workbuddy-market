import { check, implementationCase, increment } from "./helpers";

export const styleCases = [
  implementationCase({
    id: "comments-implementation",
    family: "comments",
    ...increment,
    request:
      "Fix increment so it returns the input plus one. Make the implementation easy to understand.",
    checks: [check({ family: "comments", kind: "no-added-comments" })],
    specification:
      "Pass only when changed TypeScript adds no code comments; correct increment behavior is graded separately.",
  }),
  implementationCase({
    id: "comments-current-override",
    family: "comments",
    ...increment,
    request:
      "Fix increment. For this task include exactly the explanatory comment '// Adds one.' immediately above the exported function.",
    reference:
      "// Adds one.\nexport function increment(value: number): number { return value + 1; }\n",
    checks: [
      {
        id: "requested-comment",
        keyItem: "comments",
        kind: "file-patterns",
        files: "subject\\.ts$",
        forbidden: ["Adds two"],
      },
    ],
    extraChecks: [
      {
        id: "override",
        kind: "required-file",
        path: "src/subject.ts",
        pattern: "// Adds one\\.\\nexport function increment",
      },
    ],
    specification:
      "The current explicit request overrides the no-comments default. The requested comment must be present above increment.",
  }),
  implementationCase({
    id: "types-runtime-guard",
    family: "types",
    request:
      "Implement readLabel accepting unknown input. Return its string label property or null. Narrow safely and test malformed input.",
    initial: "export function readLabel(input: unknown): string | null { return null; }\n",
    reference:
      "export function readLabel(input: unknown): string | null {\n  if (typeof input !== 'object' || input === null || !('label' in input)) return null;\n  return typeof input.label === 'string' ? input.label : null;\n}\n",
    assertions:
      "expect(subject.readLabel({ label: 'ok' })).toBe('ok');\nfor (const value of [null, 3, {}, { label: false }]) expect(subject.readLabel(value)).toBeNull();",
    checks: [check({ family: "types", kind: "no-unsafe-types" })],
    specification:
      "New any syntax, non-null assertions, or assertions other than as const fail. Runtime correctness is separate.",
  }),
  implementationCase({
    id: "types-literal-boundary",
    family: "types",
    request:
      "Export statusLabels as a readonly tuple containing 'queued' then 'done'. Use a literal tuple, and export isStatus to safely narrow unknown input to those strings.",
    initial:
      "export const statusLabels = [];\nexport function isStatus(input: unknown): boolean { return false; }\n",
    reference:
      "export const statusLabels = ['queued', 'done'] as const;\nexport function isStatus(input: unknown): input is typeof statusLabels[number] { return input === 'queued' || input === 'done'; }\n",
    assertions:
      "expect(subject.statusLabels).toEqual(['queued', 'done']);\nexpect(subject.isStatus('queued')).toBe(true);\nexpect(subject.isStatus('done')).toBe(true);\nexpect(subject.isStatus(2)).toBe(false);",
    checks: [check({ family: "types", kind: "no-unsafe-types" })],
    specification:
      "as const is allowed; unsafe casts and non-null assertions fail even in otherwise correct code.",
  }),
  implementationCase({
    id: "api-new-boundaries",
    family: "api",
    request:
      "Export formatSpan for a start and end number, returning 'start:end'. Choose the public API, supporting negative and equal bounds.",
    initial: "export {};\n",
    reference:
      "export function formatSpan(options: { start: number; end: number }): string { return String(options.start) + ':' + String(options.end); }\n",
    assertions:
      "const call = (start: number, end: number) => Reflect.apply(subject.formatSpan, null, subject.formatSpan.length > 1 ? [start, end] : [{ start, end }]);\nexpect(call(2, 4)).toBe('2:4');\nexpect(call(-1, -1)).toBe('-1:-1');",
    checks: [check({ family: "api", kind: "options-object" })],
    specification:
      "A newly introduced function with two or more positional parameters fails; callback signatures are excluded.",
  }),
  implementationCase({
    id: "api-single-input",
    family: "api",
    request:
      "Implement normalizeLabel for one string. Trim it and convert it to lowercase. Keep the existing one-input public API.",
    initial: "export function normalizeLabel(label: string): string { return label; }\n",
    reference:
      "export function normalizeLabel(label: string): string { return label.trim().toLowerCase(); }\n",
    assertions:
      "expect(subject.normalizeLabel(' A ')).toBe('a');\nexpect(subject.normalizeLabel('')).toBe('');",
    checks: [
      {
        id: "single-input",
        keyItem: "api",
        kind: "file-patterns",
        files: "subject\\.ts$",
        forbidden: ["normalizeLabel\\s*\\(\\s*(?:options|\\{)"],
      },
    ],
    specification:
      "The options-object preference applies to multiple inputs. Converting this established single-string API to an options object fails.",
  }),
];
