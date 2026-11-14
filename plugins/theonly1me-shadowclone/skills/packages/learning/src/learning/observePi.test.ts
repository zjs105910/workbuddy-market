import { expect, test } from "bun:test";
import { mkdtemp, symlink, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, createProjectPaths } from "@shadowclone/core";
import { materializeEvidence } from "../distill/excerpts";
import { ingestSources, openEventIndex, deriveSignals, observePiFile } from "@shadowclone/sessions";

const secret = ["sk", "proj", "synthetic123DEF456ghi789JKL"].join("-");
function entry(options: { readonly id: string; readonly parentId: string | null; readonly role?: string; readonly content?: unknown; readonly type?: string }) {
  return { type: options.type ?? "message", id: options.id, parentId: options.parentId,
    timestamp: "2026-10-01T09:00:00.000Z", message: { role: options.role ?? "user", content: options.content ?? "Always use complete names." } };
}

test("Pi learning follows branch ancestry through the redaction gate and excludes generated content", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-pi-capture-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const sourcePath = path.join(paths.piSessionsDirectory, "fixture/session.jsonl");
  const records = [
    { type: "session", version: 3, id: "synthetic", cwd: "/synthetic/repository" },
    entry({ id: "user", parentId: null, content: `Always redact ${secret}.` }),
    entry({ id: "assistant", parentId: "user", role: "assistant", content: [
      { type: "thinking", thinking: "excluded-thinking" }, { type: "text", text: "Original explanation" },
      { type: "toolCall", name: "read", arguments: { path: "excluded-file" } },
    ] }),
    entry({ id: "abandoned", parentId: "assistant", role: "assistant", content: "Unrelated abandoned branch" }),
    entry({ id: "result", parentId: "assistant", role: "toolResult", content: "excluded-tool-results" }),
    entry({ id: "system", parentId: "result", role: "system", content: "excluded-system" }),
    entry({ id: "summary", parentId: "system", type: "compaction", content: "excluded-summary" }),
    entry({ id: "injected", parentId: "summary", type: "custom_message", content: "excluded-injection" }),
    entry({ id: "correction", parentId: "injected", content: "Always keep function names explicit." }),
  ];
  const original = `${records.map(record => JSON.stringify(record)).join("\n")}\n`;
  await Bun.write(sourcePath, original);
  const index = await openEventIndex(":memory:");
  try {
    expect((await ingestSources({ index, paths, config: defaultConfig })).events).toBe(0);
    const config = { ...defaultConfig, sources: { ...defaultConfig.sources, pi: true } };
    await ingestSources({ index, paths, config });
    const derived = await deriveSignals({ events: index.listEvents(), corpus: index.getCorpusSummary(), gitMetadataEnabled: false });
    const evidence = await materializeEvidence({ signals: derived.learning, sourceRoots: [paths.piSessionsDirectory] });
    const text = [...evidence.excerpts.values()].join("\n");
    expect(derived.learning).toHaveLength(2);
    expect(text).toContain("[redacted:llm-api-key]");
    expect(text).not.toContain(secret);
    expect(text).toContain("Original explanation");
    expect(text).not.toContain("abandoned branch");
    for (const excluded of ["excluded-thinking", "excluded-file", "excluded-tool-results", "excluded-system", "excluded-summary", "excluded-injection"]) expect(text).not.toContain(excluded);
    expect(await Bun.file(sourcePath).text()).toBe(original);
  } finally { index.close(); await rm(home, { recursive: true, force: true }); }
});

test("Pi retains incremental parent links, waits for complete records, and refuses symlink transcripts", async () => {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-pi-incremental-"));
  const sourcePath = path.join(home, "session.jsonl");
  const header = JSON.stringify({ type: "session", version: 3, id: "fixture", cwd: "/synthetic" });
  const first = JSON.stringify(entry({ id: "first", parentId: null }));
  const next = JSON.stringify(entry({ id: "next", parentId: "first" }));
  try {
    await Bun.write(sourcePath, `${header}\n${first}\n${next}`);
    const batch = await observePiFile({ sourcePath, cursor: null });
    expect(batch?.events).toHaveLength(1);
    if (!batch) throw new Error("Missing synthetic batch");
    await Bun.write(sourcePath, `${await Bun.file(sourcePath).text()}\n`);
    const incremental = await observePiFile({ sourcePath, cursor: batch.cursor });
    expect(incremental?.events).toHaveLength(1);
    expect(incremental?.events[0]?.parentEventId).toBe("fixture:first");
    expect(incremental?.events[0]?.cwd).toBe("/synthetic");
    await symlink(sourcePath, path.join(home, "linked.jsonl"));
    expect(await observePiFile({ sourcePath: path.join(home, "linked.jsonl"), cursor: null })).toBeNull();
    await Bun.write(sourcePath, `${header}\n`);
    expect((await observePiFile({ sourcePath, cursor: batch.cursor }))?.rescanned).toBeTrue();
  } finally { await rm(home, { recursive: true, force: true }); }
});
