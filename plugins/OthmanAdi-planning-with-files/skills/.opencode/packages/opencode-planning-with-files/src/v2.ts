/** OpenCode 2.x registrations around the same planning hooks used by 1.x. */
import { tool, type Plugin as LegacyPlugin } from "@opencode-ai/plugin"
import type { Plugin } from "@opencode/plugin"
import * as path from "node:path"

type Context = Parameters<Plugin.Plugin["setup"]>[0]
type Hooks = Awaited<ReturnType<LegacyPlugin>>

export async function setupV2(context: Context, createLegacy: LegacyPlugin): Promise<() => Promise<void>> {
  const controller = new AbortController()
  const registrations: Array<{ dispose(): Promise<void> }> = []
  let events: Promise<void> | undefined

  async function sessionDirectory(sessionID: string) {
    const session = await context.session.get({ sessionID }, { signal: controller.signal })
    return { directory: path.resolve(session.location.directory, session.subpath ?? "."), parentID: session.parentID }
  }

  // The shared factory reads only directory and these two client methods.
  // Translate the v2 wire shapes here instead of duplicating gate/resolver logic.
  const hooks = await createLegacy({
    directory: context.location.directory,
    client: {
      session: {
        get: async ({ path: { id } }: { path: { id: string } }) => ({ data: await sessionDirectory(id) }),
        promptAsync: async ({ path: { id }, body }: { path: { id: string }; body: { parts: Array<{ text: string }> } }) =>
          context.session.prompt({ sessionID: id, text: body.parts.map((part) => part.text).join("\n\n") }, { signal: controller.signal }),
      },
    },
  } as unknown as Parameters<LegacyPlugin>[0], { cacheSessionInfo: false })

  async function dispose() {
    controller.abort()
    await events
    await Promise.allSettled(registrations.splice(0).reverse().map((registration) => registration.dispose()))
  }

  try {
    registrations.push(await context.session.hook("context", async (event) => {
      const output = {
        message: { id: "pwf-context" },
        parts: event.system.map((part) => ({ type: "text", text: part.text })),
      }
      const count = output.parts.length
      await hooks["chat.message"]?.(
        { sessionID: event.sessionID },
        output as Parameters<NonNullable<Hooks["chat.message"]>>[1],
      )
      for (const part of output.parts.slice(count)) event.system.push({ type: "text", text: part.text })
    }))

    registrations.push(await context.tool.hook("execute.after", async (event) => {
      if (event.status !== "completed") return
      const output = { title: "", output: "", metadata: {} }
      await hooks["tool.execute.after"]?.(
        { tool: event.tool, sessionID: event.sessionID, callID: event.id, args: event.input },
        output,
      )
      if (!output.output) return
      const content = event.result.content
      event.result = {
        ...event.result,
        content: typeof content === "string"
          ? content + output.output
          : [...(content ?? []), { type: "text", text: output.output.trim() }],
      }
    }))

    registrations.push(await context.session.hook("compaction", async (event) => {
      const output = { context: [] as string[] }
      await hooks["experimental.session.compacting"]?.({ sessionID: event.sessionID }, output)
      for (const text of output.context) event.system.push({ type: "text", text })
    }))

    registrations.push(await context.tool.transform((editor) => {
      for (const [name, definition] of Object.entries(hooks.tool ?? {})) {
        editor.add({
          name,
          description: definition.description,
          input: tool.schema.object(definition.args),
          options: { codemode: false },
          async execute(args, toolContext) {
            let directory: string
            try {
              directory = (await sessionDirectory(toolContext.sessionID)).directory
            } catch {
              return { content: JSON.stringify({ ok: false, error: "Could not resolve this session's project directory." }) }
            }
            const result = await definition.execute(args, {
              sessionID: toolContext.sessionID,
              messageID: toolContext.messageID,
              agent: toolContext.agent,
              directory,
              worktree: context.location.directory,
              abort: toolContext.signal,
              metadata: () => {},
              ask: async () => {},
            })
            return { content: typeof result === "string" ? result : result.output }
          },
        })
      }
    }))

    events = (async () => {
      try {
        for await (const event of context.event.subscribe({ signal: controller.signal })) {
          if (event.type !== "session.status" || event.data.status.type !== "idle") continue
          await hooks.event?.({ event: { type: "session.idle", properties: { sessionID: event.data.sessionID } } })
        }
      } catch {
        // Unloading or losing the event stream must not break an agent turn.
      }
    })()
    return dispose
  } catch (error) {
    await dispose()
    throw error
  }
}
