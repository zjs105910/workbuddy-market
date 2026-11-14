import type { BuildNameResult } from "../buildNameProtocol";
import type { BuildInput } from "@shadowclone/environment/browser";

export type NamerState =
  | { readonly status: "empty" }
  | { readonly status: "off" }
  | { readonly status: "unnamed" }
  | { readonly status: "waiting" }
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly result: BuildNameResult }
  | { readonly status: "failed"; readonly error: string };

export type NamerSelection = {
  readonly key: string | null;
  readonly input: BuildInput;
  readonly enabled: boolean;
  readonly changed: boolean;
};

export const namingDelayMilliseconds = 5_000;

export function createBuildNamer<Handle>(options: {
  readonly schedule: (options: { readonly run: () => void; readonly delayMilliseconds: number }) => Handle;
  readonly cancel: (handle: Handle) => void;
  readonly fetchName: (options: { readonly input: BuildInput; readonly signal: AbortSignal }) => Promise<BuildNameResult>;
  readonly onChange: (state: NamerState) => void;
}) {
  const cache = new Map<string, BuildNameResult>();
  let state: NamerState = { status: "empty" };
  let selection: NamerSelection | null = null;
  let timer: { readonly handle: Handle } | null = null;
  let inFlight: AbortController | null = null;

  const change = (next: NamerState): void => {
    state = next;
    options.onChange(next);
  };

  const stop = (): void => {
    if (timer) options.cancel(timer.handle);

    timer = null;
    inFlight?.abort();
    inFlight = null;
  };

  const run = (): void => {
    const current = selection;

    timer = null;

    if (!current?.key) return;

    const key = current.key;
    const controller = new AbortController();

    inFlight?.abort();
    inFlight = controller;
    change({ status: "loading" });
    options
      .fetchName({ input: structuredClone(current.input), signal: controller.signal })
      .then((result) => {
        cache.set(key, result);

        if (!controller.signal.aborted && selection?.key === key) change({ status: "ready", result });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted && selection?.key === key) {
          change({ status: "failed", error: error instanceof Error ? error.message : "The build could not be named." });
        }
      })
      .finally(() => {
        if (inFlight === controller) inFlight = null;
      });
  };

  return {
    state: (): NamerState => state,

    update(next: NamerSelection): void {
      const previous = selection;

      selection = next;

      if (!next.enabled) {
        stop();
        if (state.status !== "off") change({ status: "off" });

        return;
      }

      if (previous?.key === next.key && previous.enabled && state.status !== "off") return;

      stop();

      if (next.key === null) {
        change({ status: "empty" });

        return;
      }

      const cached = cache.get(next.key);

      if (cached) {
        change({ status: "ready", result: cached });

        return;
      }

      if (!next.changed) {
        change({ status: "unnamed" });

        return;
      }

      change({ status: "waiting" });
      timer = { handle: options.schedule({ run, delayMilliseconds: namingDelayMilliseconds }) };
    },

    retry(): void {
      stop();
      run();
    },
  };
}
