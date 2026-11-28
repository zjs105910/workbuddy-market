import { connect } from "node:net";

export function requestPiSocket(options: {
  readonly socketPath: string;
  readonly token: string;
  readonly request: Readonly<Record<string, unknown>>;
  readonly signal?: AbortSignal;
}): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const socket = connect(options.socketPath);
    socket.setEncoding("utf8");
    let response = "";
    let ended = false;
    const signal = AbortSignal.any([AbortSignal.timeout(300000), ...(options.signal ? [options.signal] : [])]);
    const abort = () => socket.destroy(new Error("Pi request cancelled or timed out"));
    signal.addEventListener("abort", abort, { once: true });
    if (signal.aborted) abort();
    socket.on("connect", () => socket.write(`${JSON.stringify({ token: options.token, request: options.request })}\n`));
    socket.on("data", chunk => {
      if (Buffer.byteLength(response) + Buffer.byteLength(chunk) > 1048576) {
        socket.destroy(new Error("Pi response exceeds limit"));
      } else response += chunk.toString();
    });
    socket.on("end", () => {
      ended = true;
      try { resolve(JSON.parse(response)); }
      catch { reject(new Error("Invalid Pi bridge response")); }
    });
    socket.on("error", () => reject(new Error("Pi session bridge is unavailable or cancelled")));
    socket.on("close", () => {
      signal.removeEventListener("abort", abort);
      if (!ended) reject(new Error("Pi session bridge disconnected before a response"));
    });
  });
}
