import { handleMcpRequest, isRecord, parseRequest } from "./protocol";
import { runPreferenceTool } from "./preferences";
import { runReferenceTool } from "./references";
import { createBotTool } from "./bot";
import { compileContext } from "@shadowclone/environment";
import { projectPaths } from "@shadowclone/core";
import type { ProjectPaths } from "@shadowclone/core";
import type { GitRemoteReader } from "@shadowclone/sessions";

async function activeProfile(options: {
  readonly cwd: string;
  readonly configPath?: string;
  readonly paths: ProjectPaths;
  readonly readRemote?: GitRemoteReader;
  readonly managedConfigPath?: string | null;
}): Promise<string> {
  return (await compileContext(options)) ?? "Shadowclone context is disabled.\n";
}

async function writeMessage(value: Readonly<Record<string, unknown>>): Promise<void> {
  await Bun.stdout.write(`${JSON.stringify(value)}\n`);
}

export async function serveMcp(
  options: {
    readonly cwd?: string;
    readonly configPath?: string;
    readonly paths?: ProjectPaths;
    readonly readRemote?: GitRemoteReader;
    readonly managedConfigPath?: string | null;
  } = {},
): Promise<void> {
  const cwd = options.cwd ?? process.cwd();
  const paths = options.paths ?? projectPaths;
  const botPaths = {
    ...paths,
    configFile: options.configPath ?? paths.configFile,
    managedConfigFile:
      options.managedConfigPath === undefined ? paths.managedConfigFile : options.managedConfigPath,
  };
  let buffer = "";
  const decoder = new TextDecoder();
  const bot = createBotTool({ cwd, paths: botPaths });

  for await (const chunk of Bun.stdin.stream()) {
    buffer += decoder.decode(chunk, { stream: true });

    let lineEnd = buffer.indexOf("\n");

    while (lineEnd >= 0) {
      const line = buffer.slice(0, lineEnd).trim();

      buffer = buffer.slice(lineEnd + 1);

      if (line.length > 0) {
        try {
          const request = parseRequest(JSON.parse(line));

          if (request === null) {
            await writeMessage({
              jsonrpc: "2.0",
              id: null,
              error: { code: -32600, message: "Invalid request" },
            });
          } else {
            const profile =
              request.method === "tools/call" &&
              isRecord(request.params) &&
              (request.params.name === "shadowclone_profile" ||
                request.params.name === "shadowclone_context")
                ? await activeProfile({
                    cwd,
                    configPath: options.configPath,
                    paths,
                    readRemote: options.readRemote,
                    managedConfigPath: options.managedConfigPath,
                  })
                : "";

            const toolResult =
              request.method === "tools/call"
                ? ((await bot.run(request.params)) ??
                  (await runPreferenceTool({
                    params: request.params,
                    cwd,
                    paths,
                    managedConfigPath: options.managedConfigPath,
                    readRemote: options.readRemote,
                  })) ??
                  (await runReferenceTool({
                    params: request.params,
                    cwd,
                    paths,
                    managedConfigPath: options.managedConfigPath,
                    readRemote: options.readRemote,
                  })))
                : null;

            const response = handleMcpRequest({ request, profile, toolResult });

            if (response !== null) {
              await writeMessage(response);
            }
          }
        } catch {
          await writeMessage({
            jsonrpc: "2.0",
            id: null,
            error: { code: -32700, message: "Parse error" },
          });
        }
      }

      lineEnd = buffer.indexOf("\n");
    }
  }

  bot.stop();
}

if (import.meta.main) {
  await serveMcp();
}

export { handleMcpRequest } from "./protocol";
