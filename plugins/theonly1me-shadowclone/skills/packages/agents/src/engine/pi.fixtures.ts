import { chmod, mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";

export async function piProcessFixture(options: {
  readonly text?: string;
  readonly toolCall?: boolean;
  readonly hang?: boolean;
} = {}) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "shadowclone-pi-engine-"));
  const script = path.join(directory, "pi.mjs");
  const executable = path.join(directory, "pi");
  const captured = path.join(directory, "captured.json");
  const requestLocation = path.join(directory, "request-location.txt");
  const text = options.text ?? JSON.stringify({ accepted: true });
  await Bun.write(script, `import { writeFile } from "node:fs/promises";
await writeFile(${JSON.stringify(requestLocation)}, process.env.SHADOWCLONE_PI_REQUEST);
const index = process.argv.indexOf("--extension");
const extension = await import(process.argv[index + 1]);
const model = { id: "fixture-model", provider: "custom", name: "Synthetic provider" };
extension.default({ registerCommand: async (_, command) => {
  await command.handler("", { model, modelRegistry: {
    getAvailable: () => [model],
    streamSimple: (...arguments_) => {
      writeFile(${JSON.stringify(captured)}, JSON.stringify(arguments_.slice(0, 2))).catch(() => {});
      const stream = (async function* () {
        if (${Boolean(options.hang)}) await new Promise(resolve => setTimeout(resolve, 10000));
        yield { type: "text_delta", delta: ${JSON.stringify(text)} };
      })();
      stream.result = async () => ({ stopReason: "stop", content: [
        { type: "text", text: ${JSON.stringify(text)} },
        ...(${Boolean(options.toolCall)} ? [{ type: "toolCall", name: "read" }] : [])
      ] });
      return stream;
    }
  }});
}});
`);
  const shellQuote = (value: string) => `'${value.replaceAll("'", "'\\''")}'`;
  await Bun.write(executable, `#!/bin/sh\nexec ${shellQuote(process.execPath)} ${shellQuote(script)} "$@"\n`);
  await chmod(executable, 0o700);
  return { directory, captured, requestLocation, cleanup: () => rm(directory, { recursive: true, force: true }) };
}
