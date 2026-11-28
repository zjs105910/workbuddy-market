import { expect, test } from "bun:test";
import { probeCommand } from "./detect";

test("succeeds when the probed command exits cleanly", async () => {
  expect(
    await probeCommand({ command: ["true"], timeoutMilliseconds: 5_000 }),
  ).toBeTrue();
});

test("fails a probe that does not exit before its timeout", async () => {
  const startedAt = Date.now();
  const result = await probeCommand({
    command: ["sleep", "5"],
    timeoutMilliseconds: 50,
  });

  expect(result).toBeFalse();
  expect(Date.now() - startedAt).toBeLessThan(2_000);
});

test("fails a probe for a command that does not exist", async () => {
  expect(
    await probeCommand({ command: ["shadowclone-absent-binary"] }),
  ).toBeFalse();
});
