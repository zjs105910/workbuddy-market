export function renderPiModelApi(): string {
  return `async function shadowcloneModelRequest(request, context, signal) {
    if (request.operation === "models") {
      return { models: context.modelRegistry.getAvailable().map(model => ({
        id: model.provider + "/" + model.id, name: model.name
      })) };
    }
    const available = context.modelRegistry.getAvailable();
    const model = request.model ? available.find(model => request.model === model.provider + "/" + model.id) : context.model;
    if (!model || model.id === "unknown" || typeof request.prompt !== "string") throw new Error("Unavailable model");
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) controller.abort();
    try {
      const stream = context.modelRegistry.streamSimple(model, {
        ...(request.jsonOnly ? { systemPrompt: "Return only the JSON value matching the requested schema. No Markdown fences or explanation." } : {}),
        messages: [{ role: "user", content: request.prompt, timestamp: Date.now() }], tools: []
      }, { signal: controller.signal, maxTokens: 8192, reasoning: request.reasoningEffort });
      let bytes = 0;
      for await (const event of stream) {
        if (typeof event.delta === "string") bytes += Buffer.byteLength(event.delta);
        if (bytes > 1048576) { controller.abort(); throw new Error("Response exceeds limit"); }
      }
      const result = await stream.result();
      if (result.stopReason === "error" || result.stopReason === "aborted" ||
        result.content.some(block => block.type === "toolCall")) throw new Error("Model request failed");
      const text = result.content.filter(block => block.type === "text").map(block => block.text).join("\\n");
      if (Buffer.byteLength(text) > 1048576) throw new Error("Response exceeds limit");
      return { text, model: model.provider + "/" + model.id };
    } finally { signal?.removeEventListener("abort", abort); }
  }
`;
}
