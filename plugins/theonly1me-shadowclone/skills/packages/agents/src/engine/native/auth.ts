import os from "node:os";
import path from "node:path";
import { mkdir, rm } from "node:fs/promises";
import { z } from "zod";
import { runProcess } from "@shadowclone/core";
import { runnerEnvironment } from "../environment";
import { userCodexHome } from "../codexHome";
import type { NativeEngineOptions } from "./types";

const credentialSchema = z.object({
  claudeAiOauth: z.object({ accessToken: z.string().min(1) }),
});

export async function nativeAuthentication(options: NativeEngineOptions) {
  const environment = runnerEnvironment({ engine: options.engine });
  const authenticationFile = path.join(options.homeDirectory,
    options.engine === "codex" ? ".codex/auth.json" : ".claude/.credentials.json");

  if (options.engine === "codex") {
    const source = Bun.file(path.join(userCodexHome(), "auth.json"));

    if (await source.exists()) {
      await mkdir(path.dirname(authenticationFile), { recursive: true, mode: 0o700 });
      await Bun.write(authenticationFile, source, { mode: 0o600 });
    }
  } else if (!environment.ANTHROPIC_API_KEY && !environment.CLAUDE_CODE_OAUTH_TOKEN) {
    const credentials = Bun.file(path.join(os.homedir(), ".claude", ".credentials.json"));
    const text = await credentials.exists()
      ? await credentials.text()
      : process.platform === "darwin"
        ? (await runProcess({
            arguments: ["security", "find-generic-password", "-s", "Claude Code-credentials", "-w"],
            cwd: options.homeDirectory,
            environment: { PATH: process.env.PATH },
            maximumOutputBytes: 65536,
          })).stdout
        : "";
    const parsed = credentialSchema.safeParse(JSON.parse(text || "null"));

    if (!parsed.success) {
      throw new Error("Claude authentication is unavailable for the isolated environment");
    }

    await mkdir(path.dirname(authenticationFile), { recursive: true, mode: 0o700 });
    await Bun.write(authenticationFile, text, { mode: 0o600 });
  }

  return {
    environment,
    cleanup: () => rm(authenticationFile, { force: true }),
  };
}
