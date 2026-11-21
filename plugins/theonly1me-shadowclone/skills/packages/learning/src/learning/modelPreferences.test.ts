import { expect, test } from "bun:test";
import { selectLearningPreferences } from "./modelPreferences";
import { detectEngine, getProviderSupport, getProviderByEngine } from "@shadowclone/agents";

test("explicit selection precedes session model and saved preferences without crossing harnesses", () => {
  const saved = { engine: "codex" as const, model: "saved-model" };
  const triggered = { engine: "pi" as const, model: "custom/local-model" };
  expect(selectLearningPreferences({ saved, triggered })).toEqual(triggered);
  expect(selectLearningPreferences({ saved, triggered, explicit: { model: "custom/override" } })).toEqual({ engine: "pi", model: "custom/override" });
  expect(selectLearningPreferences({ saved, triggered, explicit: { engine: "claude-code" } })).toEqual({ engine: "claude-code" });
  expect(selectLearningPreferences({ saved })).toEqual(saved);
  expect(selectLearningPreferences({})).toEqual({});
});

test("Pi detection never falls back when an explicitly selected harness is unavailable or blocked", async () => {
  const probe = async (options: { readonly command: readonly string[] }) => options.command[0] !== "pi";
  const detection = await detectEngine({ purpose: "distill", preferredEngine: "pi", probe });
  expect(detection.runner).toBeNull();
  expect((await detectEngine({ purpose: "distill", preferredEngine: "pi", probe: async () => true, allowedEngines: ["codex"] })).runner).toBeNull();
  const provider = getProviderByEngine("pi");
  if (!provider) throw new Error("Missing Pi registration");
  expect(getProviderSupport(provider)).toEqual({ observe: true, distill: true });
  expect((await detectEngine({ purpose: "eval", preferredEngine: "pi", probe: async () => true })).runner).toBeNull();
});
