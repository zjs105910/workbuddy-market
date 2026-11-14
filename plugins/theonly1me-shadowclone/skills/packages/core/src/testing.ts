import { mkdtemp } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { defaultConfig, writeConfig } from "./config";
import { seedSkillsDirectory } from "./distribution";
import { canonicalPath, createProjectPaths } from "./paths";

export async function checkoutRoot(): Promise<string> {
  return path.dirname(await seedSkillsDirectory());
}

export async function integrationFixture() {
  const home = canonicalPath(
    await mkdtemp(path.join(os.tmpdir(), "shadowclone-integration-")),
  );
  const cwd = path.join(home, "repository");
  const paths = createProjectPaths({ homeDirectory: home, platform: "darwin" });

  await Bun.write(path.join(cwd, "README.md"), "Repository fixture\n");
  await writeConfig({ config: defaultConfig, configPath: paths.configFile });
  await Bun.write(
    path.join(paths.profileDirectory, "global/engineering.md"),
    "## Naming\n\nUse complete names.\n",
  );

  return {
    home,
    cwd,
    paths,
    configPath: paths.configFile,
    managedConfigPath: null,
  };
}
