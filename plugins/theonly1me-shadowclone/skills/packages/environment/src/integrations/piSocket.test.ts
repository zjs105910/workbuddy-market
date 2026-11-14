import { expect, test } from "bun:test";
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { renderPiServer } from "./piServer";
import { requestPiSocket, detectPi } from "@shadowclone/agents";

test("the live Pi bridge uses a session-registered provider, authenticates requests, and cancels on disconnect", async () => {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-pi-socket-"));
  const modulePath = path.join(directory, "server.mjs");
  await Bun.write(modulePath, `${renderPiServer()}\nexport { serveShadowcloneModels };\n`);
  const module = await import(modulePath);
  let cancelled = false;
  let calls = 0;
  let prepared: unknown = null;
  const model = { provider: "session-extension", id: "local", name: "Synthetic local" };
  const bridge = await module.serveShadowcloneModels({ model, modelRegistry: {
    getAvailable: () => [model],
    streamSimple: (...arguments_: readonly unknown[]) => {
      calls += 1;
      prepared = arguments_[1];
      const value = arguments_[2];
      if (typeof value !== "object" || value === null || !("signal" in value) || !(value.signal instanceof AbortSignal)) throw new Error("Missing cancellation signal");
      const signal = value.signal;
      const stream = (async function* () {
        if (calls > 1) await new Promise(resolve => signal.addEventListener("abort", () => { cancelled = true; resolve(null); }, { once: true }));
        yield { type: "text_delta", delta: "Synthetic response" };
      })();
      return Object.assign(stream, { result: async () => ({ stopReason: "stop", content: [{ type: "text", text: "Synthetic response" }] }) });
    },
  }});
  const socketPath = bridge.environment.SHADOWCLONE_PI_SOCKET;
  const token = bridge.environment.SHADOWCLONE_PI_TOKEN;
  try {
    expect(await detectPi({ environment: bridge.environment })).toEqual({ engine: "pi", installed: true, authenticated: true });
    const result = await requestPiSocket({ socketPath, token, request: { model: "session-extension/local", prompt: "Prepared synthetic input" } });
    expect(result).toEqual({ text: "Synthetic response", model: "session-extension/local" });
    expect(prepared).toMatchObject({ messages: [{ role: "user", content: "Prepared synthetic input" }], tools: [] });
    await expect(requestPiSocket({ socketPath, token: "wrong-token", request: { prompt: "Unauthorized" } })).rejects.toThrow();
    expect(calls).toBe(1);
    expect(await requestPiSocket({ socketPath, token, signal: AbortSignal.timeout(500), request: { model: "session-extension/missing", prompt: "Synthetic" } })).toHaveProperty("error");
    expect(calls).toBe(1);
    await expect(requestPiSocket({ socketPath, token, request: { prompt: "Synthetic" }, signal: AbortSignal.timeout(80) })).rejects.toThrow("cancelled");
    await new Promise(resolve => setTimeout(resolve, 20));
    expect(cancelled).toBeTrue();
  } finally { await bridge.close(); await rm(directory, { recursive: true, force: true }); }
});
