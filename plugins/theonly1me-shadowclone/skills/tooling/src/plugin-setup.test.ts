import { expect, test } from "bun:test";
import { chmod, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { z } from "zod";

const resultSchema = z.object({
  version: z.string().nullable(), minimumVersion: z.literal("0.0.13"),
  status: z.enum(["ready", "outdated", "unavailable"]),
});
const helper = path.resolve(
  import.meta.dir,
  "../../plugins/shadowclone/skills/setup-shadowclone/scripts/check-cli.mjs",
);
const node = Bun.which("node");
if (!node) throw new Error("Node is required to verify the plugin setup helper");

for (const [version, expected] of [
  ["0.0.12", "outdated"], ["0.0.13", "ready"], ["0.1.0", "ready"],
  ["1.0.0", "ready"], ["0.0.13-beta.1", "unavailable"], ["unexpected diagnostic", "unavailable"],
] as const) {
  test(`setup checks ${version} before reading configuration`, async () => {
    const root = await mkdtemp(path.join(os.tmpdir(), "shadowclone-plugin-version-"));
    try {
      const executable = path.join(root, "shadowclone");
      await Bun.write(executable, `#!/bin/sh\n[ "$1" = "--version" ] || exit 7\nprintf '%s\\n' '${version}'\n`);
      await chmod(executable, 0o755);
      const child = Bun.spawn([node, helper], {
        env: { PATH: root }, stdout: "pipe", stderr: "pipe",
      });
      const result = resultSchema.parse(await new Response(child.stdout).json());
      expect(result.status).toBe(expected);
      expect(result.version).toBe(expected === "unavailable" ? null : version);
      expect(await child.exited).toBe(0);
      expect(await new Response(child.stderr).text()).toBe("");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
}

test("missing CLI yields a bounded install decision", async () => {
  const child = Bun.spawn([node, helper], {
    env: { PATH: "/nonexistent" }, stdout: "pipe", stderr: "pipe",
  });
  expect(resultSchema.parse(await new Response(child.stdout).json()).status).toBe("unavailable");
  expect(await child.exited).toBe(0);
  expect(await new Response(child.stderr).text()).toBe("");
});
