import { mkdir } from "node:fs/promises";
import path from "node:path";
import { createProjectPaths, ownedWrite } from "@shadowclone/core";
import { emptyEnvironment, renderSkillRouting, skillPublication } from "@shadowclone/environment";
import { nativeFileSchema } from "../native/schema";
import { captureArm } from "../native/study/prepare/freeze";
import { fingerprint } from "../shared/structured";
import { profileText } from "./fixtures/profile";
import type { NativeEngine } from "@shadowclone/agents";

export async function fixedArmEnvironments(options: { directory: string; engine: NativeEngine }) {
  const home = path.join(options.directory, "publication-home");
  const workspace = path.join(options.directory, "publication-workspace");
  await mkdir(home, { recursive: true, mode: 0o700 });
  await mkdir(workspace, { mode: 0o700 });
  const paths = createProjectPaths({ homeDirectory: home, platform: process.platform });
  const scope = { key: "global", directory: home, repository: null };
  const publication = await skillPublication({
    paths, state: { ...emptyEnvironment, phase: "active" }, scope, skill: null, records: [],
    name: "engineering-preferences",
    text: `---\nname: engineering-preferences\ndescription: Apply personal standards when changing code or answering engineering questions.\n---\n\n# Engineering preferences\n\n${profileText}`,
  });
  for (const update of publication.updates) {
    if (update.next !== null) await ownedWrite({ path: update.filePath, content: update.next });
  }
  const instructionPath = options.engine === "codex" ? ".codex/AGENTS.md" : ".claude/CLAUDE.md";
  await ownedWrite({ path: path.join(home, instructionPath), content: renderSkillRouting({ state: publication.state, scopes: [scope] }) });
  const shadowclone = await captureArm({ home, workspace, sourceHome: home, engine: options.engine });
  const files = [nativeFileSchema.parse({ root: "home", path: instructionPath, content: profileText })];
  return { original: { files, fingerprint: fingerprint(files) }, "first-time": shadowclone, deep: { files: [], fingerprint: fingerprint([]) } };
}
