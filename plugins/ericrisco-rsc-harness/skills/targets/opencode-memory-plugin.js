// rsc-memory:managed
// One file for both OpenCode plugin APIs (issue #289). V1 (1.x) calls the named export, or the default
// export's server(); V2 (2.x) reads the default export's id + setup(ctx) and ignores the rest.
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { capture, resume } from '../../.rsc/session-memory-core.mjs';

function memorySettings(cwd) {
  try {
    const value = JSON.parse(readFileSync(join(cwd, '.rsc.json'), 'utf8')).memory;
    if (value === false) return { enabled: false };
    return value && typeof value === 'object' ? value : {};
  } catch {
    return {};
  }
}

function sessionId(input) {
  return input?.sessionID || input?.session_id || input?.event?.properties?.info?.id
    || input?.event?.properties?.sessionID || input?.event?.data?.sessionID || null;
}

/** What the plugin does, whichever API delivers the moment. `put(text)` adds to the system prompt. */
function memory(cwd) {
  const injected = new Set();
  const local = () => process.env.RSC_REMOTE_AGENT !== '1' && process.env.OPENCODE_REMOTE !== '1';
  const save = (id, event, editDelta = 0) => {
    if (!id || !local()) return;
    try { capture({ cwd, sessionId: id, target: 'opencode', event, editDelta, settings: memorySettings(cwd) }); } catch { /* fail open */ }
  };
  return {
    save,
    context(id, put) {
      if (!id || injected.has(id) || !local()) return;
      injected.add(id);
      try {
        save(id, 'start');
        const result = resume({ cwd, target: 'opencode', settings: memorySettings(cwd) });
        if (result.context) put(result.context);
      } catch { /* fail open */ }
    },
    tool(id, name) {
      save(id, 'boundary', /write|edit|patch/u.test(String(name || '').toLowerCase()) ? 1 : 0);
    },
    compact(id, put) {
      save(id, 'compact');
      try {
        const result = resume({ cwd, target: 'opencode', settings: memorySettings(cwd) });
        if (result.context) put(result.context);
      } catch { /* fail open */ }
    },
  };
}

// ---------------------------------------------------------------- OpenCode 1.x (V1 plugin API)

export const RscMemoryPlugin = async ({ directory, worktree }) => {
  const m = memory(worktree || directory);
  return {
    'experimental.chat.system.transform': async (input, output) => {
      if (!Array.isArray(output?.system)) return;
      m.context(sessionId(input), (text) => {
        if (output.system.length === 0) output.system.push(text);
        else output.system[0] = `${output.system[0]}\n\n${text}`;
      });
    },
    'tool.execute.after': async (input) => m.tool(sessionId(input), input?.tool),
    'experimental.session.compacting': async (input, output) => {
      m.compact(sessionId(input), (text) => { if (Array.isArray(output?.context)) output.context.push(text); });
    },
    event: async ({ event }) => {
      const id = sessionId({ event });
      if (event?.type === 'session.created') m.save(id, 'start');
      else if (event?.type === 'file.edited') m.save(id, 'edit', 1);
      else if (event?.type === 'session.compacted') m.save(id, 'compact');
      else if (event?.type === 'session.idle') m.save(id, 'turn');
      else if (event?.type === 'session.deleted') m.save(id, 'sessionEnd');
    },
  };
};

// ---------------------------------------------------------------- OpenCode 2.x (V2 plugin API)
// Hooks register through the context; the end of a turn is `session.execution.*` (there is no
// `session.idle`), and every event carries its session in `data.sessionID`.

const TURN_END = new Set(['session.execution.succeeded', 'session.execution.failed']);

export default {
  id: 'rsc.memory',
  server: RscMemoryPlugin,
  async setup(ctx) {
    const m = memory(ctx.location?.project?.directory || ctx.location?.directory || process.cwd());
    const part = (event) => (text) => { if (Array.isArray(event?.system)) event.system.push({ type: 'text', text }); };
    await ctx.session.hook('context', async (event) => m.context(event?.sessionID, part(event)));
    await ctx.session.hook('compaction', async (event) => m.compact(event?.sessionID, part(event)));
    await ctx.tool.hook('execute.after', async (event) => m.tool(event?.sessionID, event?.tool));
    const stop = new AbortController();
    (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: stop.signal })) {
          const id = event?.data?.sessionID;
          if (event?.type === 'session.created') m.save(id, 'start');
          else if (TURN_END.has(event?.type)) m.save(id, 'turn');
          else if (event?.type === 'session.deleted') m.save(id, 'sessionEnd');
        }
      } catch { /* unloading, or the stream ended: fail open */ }
    })();
    return () => stop.abort();
  },
};
