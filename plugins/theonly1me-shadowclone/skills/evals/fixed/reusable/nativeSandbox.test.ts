import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fixedCliVersion } from "../identity";
import { qualifyCodexSandbox } from "./nativeSandbox";

test.skipIf(process.platform !== "darwin" || !Bun.which("codex"))(
  "native Codex denies unrelated temporary access in every candidate permission mode",
  async () => {
    const directory = await mkdtemp(path.join(os.tmpdir(), "v3-native-sandbox-"));
    try {
      const result = await qualifyCodexSandbox({
        outputDirectory: directory,
        expectedCliVersion: await fixedCliVersion("codex"),
      });
      expect(result.probes).toHaveLength(4);
      expect(result).toMatchObject({ passed: true, modelCalls: 0 });
      expect(result.probes.every((probe) => probe.passed)).toBe(true);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  },
  30000,
);
