import { cp, mkdir, readdir } from "node:fs/promises";
import path from "node:path";
import { isolateNativeGuidance } from "../../../shared/nativeIsolation";

const skillRoots = [".agents/skills", ".claude/skills", ".codex/skills"] as const;
const instructionFiles = [".claude/CLAUDE.md", ".codex/AGENTS.md", ".codex/AGENTS.override.md"] as const;

export async function copyPersonalLibrary(options: {
  readonly sourceHome: string;
  readonly targetHome: string;
}): Promise<{ readonly skills: number }> {
  let skills = 0;

  for (const root of skillRoots) {
    const sourceRoot = path.join(options.sourceHome, root);
    const entries = await readdir(sourceRoot, { withFileTypes: true }).catch(() => []);

    for (const entry of entries) {
      if (!entry.isDirectory() || entry.name.startsWith(".") || entry.name.startsWith("shadowclone")) {
        continue;
      }

      const source = path.join(sourceRoot, entry.name);

      if (!await Bun.file(path.join(source, "SKILL.md")).exists()) {
        continue;
      }

      await cp(source, path.join(options.targetHome, root, entry.name), { recursive: true, dereference: true });
      skills += 1;
    }
  }

  for (const relative of instructionFiles) {
    const source = path.join(options.sourceHome, relative);

    if (!await Bun.file(source).exists()) {
      continue;
    }

    const destination = path.join(options.targetHome, relative);
    await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 });
    await cp(source, destination);
  }

  await isolateNativeGuidance(options.targetHome);
  return { skills };
}
