import { implementationCase } from "./cases/helpers";

export const routingLibrary = [
  {
    name: "settlement-contracts",
    description: "Conventions for financial service changes and data exchanges.",
    trigger: "settlement",
    rule: "New settlement functions accept one options object for multiple inputs.",
    kind: "options-object",
  },
  {
    name: "refund-contracts",
    description: "Conventions for financial service changes and data exchanges.",
    trigger: "refund",
    rule: "Refund code explains itself through names. Add no code comments.",
    kind: "no-added-comments",
  },
  {
    name: "ledger-contracts",
    description: "Conventions for financial service changes and data exchanges.",
    trigger: "ledger",
    rule: "Ledger inputs must be narrowed safely. Use no any, type casts, or non-null assertions.",
    kind: "no-unsafe-types",
  },
  {
    name: "shipment-contracts",
    description: "Working conventions for operational modules and records.",
    trigger: "shipment",
    rule: "Shipment functions taking multiple inputs use an options object.",
    kind: "options-object",
  },
  {
    name: "inventory-contracts",
    description: "Working conventions for operational modules and records.",
    trigger: "inventory",
    rule: "Inventory changes add no code comments, using clear names instead.",
    kind: "no-added-comments",
  },
  {
    name: "reservation-contracts",
    description: "Working conventions for operational modules and records.",
    trigger: "reservation",
    rule: "Reservation data stays type-safe. Avoid any, casts, and non-null assertions.",
    kind: "no-unsafe-types",
  },
  {
    name: "subscription-contracts",
    description: "Conventions for customer lifecycle modules.",
    trigger: "subscription",
    rule: "Subscription functions with multiple inputs take one options object.",
    kind: "options-object",
  },
  {
    name: "entitlement-contracts",
    description: "Conventions for customer lifecycle modules.",
    trigger: "entitlement",
    rule: "Do not introduce code comments in entitlement changes.",
    kind: "no-added-comments",
  },
  {
    name: "account-contracts",
    description: "Conventions for customer lifecycle modules.",
    trigger: "account",
    rule: "Narrow unknown account data without any or assertions except as const.",
    kind: "no-unsafe-types",
  },
  {
    name: "telemetry-contracts",
    description: "Conventions for infrastructure service changes.",
    trigger: "telemetry",
    rule: "Telemetry operations take an options object when accepting multiple inputs.",
    kind: "options-object",
  },
  {
    name: "scheduler-contracts",
    description: "Conventions for infrastructure service changes.",
    trigger: "scheduler",
    rule: "Avoid code comments in scheduler implementations.",
    kind: "no-added-comments",
  },
  {
    name: "cache-contracts",
    description: "Conventions for infrastructure service changes.",
    trigger: "cache",
    rule: "Cache code must use safe narrowing, without any, casts, or non-null assertions.",
    kind: "no-unsafe-types",
  },
  {
    name: "payments-contracts",
    description: "Conventions for financial service changes and data exchanges.",
    trigger: "payments",
    rule: "Payment receipts use ISO dates.",
    kind: "no-added-comments",
  },
  {
    name: "billing-contracts",
    description: "Conventions for financial service changes and data exchanges.",
    trigger: "billing",
    rule: "Billing output orders currencies alphabetically.",
    kind: "no-added-comments",
  },
  {
    name: "warehouse-contracts",
    description: "Working conventions for operational modules and records.",
    trigger: "warehouse",
    rule: "Warehouse identifiers are case-sensitive.",
    kind: "no-added-comments",
  },
  {
    name: "dispatch-contracts",
    description: "Working conventions for operational modules and records.",
    trigger: "dispatch",
    rule: "Dispatch timestamps use UTC.",
    kind: "no-added-comments",
  },
  {
    name: "identity-contracts",
    description: "Conventions for customer lifecycle modules.",
    trigger: "identity",
    rule: "Identity display names preserve spelling.",
    kind: "no-added-comments",
  },
  {
    name: "profile-contracts",
    description: "Conventions for customer lifecycle modules.",
    trigger: "profile",
    rule: "Profile updates preserve omitted fields.",
    kind: "no-added-comments",
  },
  {
    name: "storage-contracts",
    description: "Conventions for infrastructure service changes.",
    trigger: "storage",
    rule: "Storage keys preserve letter case.",
    kind: "no-added-comments",
  },
  {
    name: "queue-contracts",
    description: "Conventions for infrastructure service changes.",
    trigger: "queue",
    rule: "Queue status output lists oldest entries first.",
    kind: "no-added-comments",
  },
] as const;

export const routingSkill = (skill: (typeof routingLibrary)[number]) =>
  `---\nname: ${skill.name}\ndescription: ${skill.description}\n---\n\n# ${skill.trigger} changes\n\nApply only to ${skill.trigger} modules.\n${skill.rule}\n`;
export const routingCases = routingLibrary.slice(0, 12).map((skill) => {
  const typedInput = skill.kind === "no-unsafe-types";
  const source = typedInput
    ? "export function readName(input: unknown): string | null { return null; }\n"
    : "export {};\n";
  const reference = typedInput
    ? "export function readName(input: unknown): string | null { if (typeof input !== 'object' || input === null || !('name' in input)) return null; return typeof input.name === 'string' ? input.name : null; }\n"
    : "export function joinNames(options: { first: string; second: string }): string { return options.first + ':' + options.second; }\n";
  return {
    expectedSkill: skill.name,
    case: implementationCase({
      id: `routing-${skill.trigger}`,
      family: typedInput ? "types" : skill.kind === "options-object" ? "api" : "comments",
      request: typedInput
        ? `In the ${skill.trigger} module implement readName for unknown data. Return its string name property or null and test malformed inputs.`
        : `In the ${skill.trigger} module export joinNames for two strings. Return first:second. Choose a clear public API and make the code easy to understand.`,
      initial: source,
      reference,
      assertions: typedInput
        ? "expect(subject.readName({ name: 'a' })).toBe('a');\nexpect(subject.readName(null)).toBeNull();\nexpect(subject.readName({ name: 1 })).toBeNull();"
        : "const call = () => Reflect.apply(subject.joinNames, null, subject.joinNames.length > 1 ? ['a', 'b'] : [{ first: 'a', second: 'b' }]);\nexpect(call()).toBe('a:b');",
      checks: [
        {
          id: "compliance",
          keyItem: typedInput ? "types" : skill.kind === "options-object" ? "api" : "comments",
          kind: skill.kind,
        },
      ],
      specification: `Selection requires reading ${skill.name} and no unrelated contract. Compliance independently grades ${skill.kind}; reading alone earns no compliance credit.`,
    }),
  };
});
