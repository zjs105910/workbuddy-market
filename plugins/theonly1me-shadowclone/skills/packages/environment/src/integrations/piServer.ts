import { renderPiModelApi } from "@shadowclone/agents";

export function renderPiServer(): string {
  return `import { createServer } from "node:net";
import { mkdtemp, chmod, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { randomUUID } from "node:crypto";
${renderPiModelApi()}
async function serveShadowcloneModels(context) {
  const directory = await mkdtemp(join(tmpdir(), "shadowclone-pi-session-"));
  await chmod(directory, 0o700);
  const socketPath = join(directory, "models.sock");
  const token = randomUUID();
  let currentContext = context;
  const server = createServer(socket => {
    socket.setEncoding("utf8");
    let input = "";
    let dispatched = false;
    const controller = new AbortController();
    socket.on("close", () => controller.abort());
    socket.on("error", () => controller.abort());
    socket.setTimeout(300000, () => socket.destroy());
    socket.on("data", async chunk => {
      if (dispatched) return;
      if (Buffer.byteLength(input) + Buffer.byteLength(chunk) > 1048576) { socket.destroy(); return; }
      input += chunk.toString();
      if (!input.endsWith("\\n")) return;
      dispatched = true;
      try {
        const message = JSON.parse(input);
        if (message.token !== token) { socket.destroy(); return; }
        const result = await shadowcloneModelRequest(message.request, currentContext, controller.signal);
        socket.end(JSON.stringify(result));
      } catch {
        socket.end(JSON.stringify({ error: "Pi model request failed; check the selected model in Pi" }));
      }
    });
  });
  try {
    await new Promise((resolve, reject) => { server.once("error", reject); server.listen(socketPath, resolve); });
  } catch (error) {
    await rm(directory, { recursive: true, force: true });
    throw error;
  }
  return {
    environment: { SHADOWCLONE_PI_SOCKET: socketPath, SHADOWCLONE_PI_TOKEN: token },
    update: context => { currentContext = context; },
    close: async () => {
      await new Promise(resolve => server.close(resolve));
      await rm(directory, { recursive: true, force: true });
    }
  };
}
`;
}
