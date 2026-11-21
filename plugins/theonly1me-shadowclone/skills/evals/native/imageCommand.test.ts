import { expect, test } from "bun:test";
import { NativeInfrastructureError } from "./diagnostics";
import { imageCommand } from "./imageCommand";

function scriptedRun(exitCodes: readonly number[]) {
  const calls: (readonly string[])[] = [];
  const run = async (options: { readonly arguments: readonly string[] }) => {
    calls.push(options.arguments);

    return { exitCode: exitCodes[calls.length - 1] ?? 1, stdout: "", stderr: "Resource busy" };
  };

  return { calls, run };
}

test("a transient hdiutil failure succeeds on the next attempt", async () => {
  const fixture = scriptedRun([1, 0]);

  await imageCommand({
    arguments: ["attach", "image.dmg"],
    directory: "/synthetic",
    stage: "mount-attach",
    run: fixture.run,
    pauseMilliseconds: 0,
  });

  expect(fixture.calls).toEqual([
    ["attach", "image.dmg"],
    ["attach", "image.dmg"],
  ]);
});

test("detach forces only its last attempt and reports every failure", async () => {
  const fixture = scriptedRun([1, 1, 1]);
  const failure = await imageCommand({
    arguments: ["detach", "/synthetic/mounted"],
    directory: "/synthetic",
    stage: "mount-detach",
    forceOnLastAttempt: true,
    run: fixture.run,
    pauseMilliseconds: 0,
  }).catch((error: unknown) => error);

  expect(fixture.calls.map((call) => call.includes("-force"))).toEqual([false, false, true]);
  expect(failure).toBeInstanceOf(NativeInfrastructureError);

  if (!(failure instanceof NativeInfrastructureError)) {
    throw new Error("The failure is not classified as infrastructure.");
  }

  expect(failure.diagnostic.stage).toBe("mount-detach");
  expect(failure.diagnostic.details.match(/attempt \d: hdiutil exit 1/g)).toHaveLength(3);
});
