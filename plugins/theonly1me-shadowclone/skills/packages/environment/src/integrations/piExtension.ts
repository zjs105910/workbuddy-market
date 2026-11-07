import path from "node:path";
import type { Integration } from "./types";
import { renderPiServer } from "./piServer";

export function renderPiExtension(integration: Integration): string {
  const launcher = path.join(integration.userDirectory, ".shadowclone", "bin", "shadowclone");
  return `import { spawn } from "node:child_process";
${renderPiServer()}
export default function (pi) {
  if (process.env.SHADOWCLONE_INTERNAL_RUN === "1") return;
  let routing = "";
  let bridge;
  let pending = Promise.resolve();
  const sessionInput = context => JSON.stringify({
      cwd: context.cwd, session_id: context.sessionManager.getSessionId(),
      model: context.model ? context.model.provider + "/" + context.model.id : undefined,
      engine: "pi", timestamp: Date.now()
    });
  const invoke = async ({ event, input }) => {
    await new Promise(resolve => {
      const child = spawn("sh", [${JSON.stringify(launcher)}, "hook", event, ${JSON.stringify(integration.id)}], {
        stdio: ["pipe", "pipe", "ignore"], timeout: event === "native-end" ? 310000 : 10000,
        env: { ...process.env, ...bridge?.environment }
      });
      let output = "";
      child.stdout.on("data", chunk => {
        if (output.length + chunk.length > 65536) child.kill();
        else output += chunk.toString();
      });
      child.on("error", resolve);
      child.on("close", () => {
        if (event === "native-start") {
          try { routing = JSON.parse(output).additionalContext || ""; }
          catch { routing = ""; }
        }
        resolve();
      });
      child.stdin.on("error", () => {});
      child.stdin.end(input);
    });
  };
  const start = async (_, context) => {
    if (bridge) bridge.update(context);
    else bridge = await serveShadowcloneModels(context);
    await invoke({ event: "native-start", input: sessionInput(context) });
  };
  pi.on("session_start", start);
  pi.on("session_switch", start);
  pi.on("before_agent_start", async event => routing ? { systemPrompt: event.systemPrompt + "\\n\\n" + routing } : undefined);
  pi.on("agent_settled", (_, context) => {
    bridge?.update(context);
    const input = sessionInput(context);
    pending = pending.then(() => invoke({ event: "native-end", input })).catch(() => {});
  });
  pi.on("session_shutdown", async (_, context) => {
    await pending;
    await invoke({ event: "native-end", input: sessionInput(context) });
    await bridge?.close();
  });
}
`;
}
