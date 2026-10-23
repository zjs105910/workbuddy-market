import { renderPiModelApi } from "./piModelApi";

export function renderPiBridge(): string {
  return `import { readFile, writeFile } from "node:fs/promises";
${renderPiModelApi()}
export default function (pi) {
  if (!process.env.SHADOWCLONE_PI_REQUEST) return;
  pi.registerCommand("shadowclone-request", { handler: async (_, context) => {
    const destination = process.env.SHADOWCLONE_PI_RESULT;
    if (!destination) throw new Error("Missing Shadowclone result destination");
    try {
      const input = await readFile(process.env.SHADOWCLONE_PI_REQUEST, "utf8");
      if (Buffer.byteLength(input) > 1048576) throw new Error("Request exceeds limit");
      const result = await shadowcloneModelRequest(JSON.parse(input), context, context.signal);
      await writeFile(destination, JSON.stringify(result), { mode: 0o600 });
    } catch {
      await writeFile(destination, JSON.stringify({ error: "Pi model request failed; check the selected model in Pi" }), { mode: 0o600 });
    }
  }});
}
`;
}
