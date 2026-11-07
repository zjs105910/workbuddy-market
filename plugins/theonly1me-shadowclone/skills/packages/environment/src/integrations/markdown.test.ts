import { expect, test } from "bun:test";
import { renderInstructionPointer } from "./markdown";

test("the instruction pointer stays three lines without routing or learning instructions", () => {
  const pointer = renderInstructionPointer();

  expect(pointer.split("\n")).toHaveLength(3);
  expect(pointer).toContain("run `shadowclone context`");
  expect(pointer).not.toContain("skill");
  expect(pointer).not.toContain("learn");
});
