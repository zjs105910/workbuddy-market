import { expect, test } from "bun:test";
import { createBotTool } from "./bot";
import { guidanceFixture } from "@shadowclone/cloud/testing";

test("MCP offers setup and saved status but rejects credential and activation operations", async () => {
  const fixture = await guidanceFixture();
  const bot = createBotTool(fixture);

  try {
    const status = await bot.run({ name: "shadowclone_bot", arguments: { operation: "status" } });

    expect(status?.isError).toBeFalse();
    expect(status?.content).toEqual([{ type: "text", text: "[]" }]);

    for (const arguments_ of [
      { operation: "activate" },
      { operation: "setup", token: "synthetic-token" },
    ]) {
      const result = await bot.run({ name: "shadowclone_bot", arguments: arguments_ });

      expect(result?.isError).toBeTrue();
    }
  } finally {
    bot.stop();
    await fixture.cleanup();
  }
});
