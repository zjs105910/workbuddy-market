import { expect, test } from "bun:test";
import { inlineCode } from "./format";

test("inline code joins each whitespace run that holds a newline into one space", () => {
  expect(inlineCode("first line \n\t second line")).toBe("`first line second line`");
  expect(inlineCode("keep  two spaces\r\nand\n\nthis")).toBe("`keep  two spaces and this`");
});

test("inline code takes linear time on a long run of spaces without a newline", () => {
  const text = `${" ".repeat(100_000)}x`;
  const started = performance.now();
  const formatted = inlineCode(text);

  expect(performance.now() - started).toBeLessThan(1_000);
  expect(formatted).toBe(`\`${text}\``);
});
