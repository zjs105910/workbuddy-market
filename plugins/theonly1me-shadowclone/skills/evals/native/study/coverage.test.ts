import { expect, test } from "bun:test";
import type { NativeFile } from "../schema";
import { coverageGate, routeOf, transferVerifiedCoverage, verifyCoverage } from "./coverage";
import type { KeyItem } from "./schema";

const keyItems: KeyItem[] = [
  { id: "no-comments", group: "personal", statement: "Do not add code comments.", evidence: "synthetic" },
  { id: "short-replies", group: "learned", statement: "Reply to review bots in one sentence.", evidence: "synthetic" },
  { id: "draft-pull-requests", group: "learned", statement: "Open pull requests as drafts.", evidence: "synthetic" },
];

const routing: NativeFile = {
  root: "home", path: ".codex/AGENTS.md", encoding: "utf8", mode: 0o600,
  content: "Before every task, read .agents/skills/baseline/SKILL.md.\n",
};
const baseline: NativeFile = {
  root: "home", path: ".agents/skills/baseline/SKILL.md", encoding: "utf8", mode: 0o600,
  content: "---\nname: baseline\n---\nAnswer review bots in one short sentence.\n",
};
const hidden: NativeFile = {
  root: "home", path: ".agents/skills/style/SKILL.md", encoding: "utf8", mode: 0o600,
  content: "---\nname: style\ndisable-model-invocation: true\n---\nNever add code comments to new code.\n",
};

test("credits coverage only for verbatim quotes and records the route", () => {
  const documents = [routing, baseline, hidden];
  const entries = verifyCoverage({
    keyItems, documents,
    audit: { items: [
      { id: "no-comments", status: "covered", file: "home/.agents/skills/style/SKILL.md", quote: "Never add code comments to new code." },
      { id: "short-replies", status: "covered", file: "home/.agents/skills/baseline/SKILL.md", quote: "answer review bots in one short   sentence." },
      { id: "draft-pull-requests", status: "covered", file: "home/.agents/skills/baseline/SKILL.md", quote: "Always open pull requests as drafts." },
    ] },
  });

  expect(entries).toEqual([
    { keyItem: "no-comments", status: "covered", file: "home/.agents/skills/style/SKILL.md", route: "not-invocable", quote: "Never add code comments to new code." },
    { keyItem: "short-replies", status: "covered", file: "home/.agents/skills/baseline/SKILL.md", route: "always-read", quote: "answer review bots in one short   sentence." },
    { keyItem: "draft-pull-requests", status: "unknown", file: "home/.agents/skills/baseline/SKILL.md", route: "none", quote: null },
  ]);
});

test("routes description-only skills separately from always-read guidance", () => {
  const described: NativeFile = { ...baseline, path: ".agents/skills/other/SKILL.md" };
  expect(routeOf({ file: described, documents: [routing, described] })).toBe("description-routed");
  expect(routeOf({ file: routing, documents: [routing] })).toBe("always-read");
});

test("the gate requires deep to cover a key item first-time lacks", () => {
  const entry = (keyItem: string, status: "covered" | "absent") => ({ keyItem, status, file: null, route: "none" as const, quote: null });
  const same = { original: [entry("no-comments", "covered")], "first-time": [entry("no-comments", "covered")], deep: [entry("no-comments", "covered")] };
  expect(coverageGate(same)).toEqual({ passed: false, deepOnly: [] });
  expect(coverageGate({ ...same, deep: [...same.deep, entry("short-replies", "covered")] }))
    .toEqual({ passed: true, deepOnly: ["short-replies"] });
});

test("a verified quote transfers to an arm carrying the same guidance file", () => {
  const environment = { files: [routing, baseline], fingerprint: "0".repeat(64) };
  const covered = { keyItem: "short-replies", status: "covered" as const, file: "home/.agents/skills/baseline/SKILL.md", route: "always-read" as const, quote: "Answer review bots in one short sentence." };
  const unknown = { keyItem: "short-replies", status: "unknown" as const, file: null, route: "none" as const, quote: null };
  const result = transferVerifiedCoverage({
    coverage: { original: [unknown], "first-time": [covered], deep: [unknown] },
    arms: { original: { files: [routing], fingerprint: "0".repeat(64) }, "first-time": environment, deep: environment },
  });
  expect(result.deep[0]?.status).toBe("covered");
  expect(result.original[0]?.status).toBe("unknown");
});
