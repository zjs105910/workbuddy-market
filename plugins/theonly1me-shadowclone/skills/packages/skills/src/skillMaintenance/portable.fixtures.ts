import { mkdir, mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createProjectPaths } from "@shadowclone/core";
import { registerPortableSkill } from "./portable";

export async function portableFixture() {
  const home = await mkdtemp(path.join(os.tmpdir(), "shadowclone-portable-"));
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });
  const sourceDirectory = path.join(home, "seed/portable-workflow");

  await mkdir(path.join(sourceDirectory, "references"), { recursive: true });
  await Bun.write(
    path.join(sourceDirectory, "SKILL.md"),
    "---\nname: portable-workflow\ndescription: Keep a workflow consistent across coding agents.\n---\n\n# Portable workflow\n\nRead [the checklist](references/checklist.md).\n",
  );
  await Bun.write(
    path.join(sourceDirectory, "references/checklist.md"),
    "Verify the requested behavior.\n",
  );

  const destinations = [
    path.join(home, ".agents/skills/portable-workflow"),
    path.join(home, ".claude/skills/portable-workflow"),
    path.join(home, ".gemini/config/skills/portable-workflow"),
  ];

  await registerPortableSkill({
    paths,
    name: "portable-workflow",
    sourceDirectory,
    managedBy: "adopted",
  });

  return { home, paths, destinations };
}
