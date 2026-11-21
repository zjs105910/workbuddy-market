import { expect, test } from "bun:test";
import { verificationFailure } from "./verification";

test("sandbox startup errors remain infrastructure gaps rather than failed model work", () => {
  expect(verificationFailure({ exitCode: 71, stderr: "sandbox-exec: sandbox_apply: Operation not permitted\n" })).toBe("unknown");
  expect(verificationFailure({ exitCode: 1, stderr: "Expected 15 but received 20" })).toBe("fail");
  expect(verificationFailure({ exitCode: 71, stderr: "Program exited without a result" })).toBe("fail");
});
