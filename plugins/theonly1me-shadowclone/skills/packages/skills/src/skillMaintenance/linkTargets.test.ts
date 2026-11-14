import { expect, test } from "bun:test";
import { markdownLinkTargets } from "./linkTargets";

function previousTargets(text: string): readonly string[] {
  return [...text.matchAll(/\]\(([^\s)#]+)(?:#[^)]*)?\)/g)].flatMap((match) =>
    match[1] ? [match[1]] : [],
  );
}

const craftedInputs = [
  "See [the guide](references/guide.md) and [the notes](notes.md#setup).",
  "[a](b#c) [d](e f) [g]() [h](#i) [j](k#l",
  "](a](b) ](c#d](e) ]](f)",
  "[x](https://example.com/a) [y](scripts/run.sh)\n[z](assets/a b.png)",
  "](a#)",
  "](a#b\nc)",
];

function generatedInputs(count: number): readonly string[] {
  const alphabet = "]()# \na!";
  const inputs: string[] = [];
  let seed = 7;

  for (let inputIndex = 0; inputIndex < count; inputIndex += 1) {
    let text = "";

    for (let characterIndex = 0; characterIndex < 24; characterIndex += 1) {
      seed = (seed * 48_271) % 2_147_483_647;
      text += alphabet.charAt(seed % alphabet.length);
    }

    inputs.push(text);
  }

  return inputs;
}

test("link targets match the previous regular expression on crafted and generated markdown", () => {
  for (const text of [...craftedInputs, ...generatedInputs(5_000)]) {
    expect(markdownLinkTargets(text)).toEqual(previousTargets(text));
  }
});

test("link targets take linear time on many link openers that never close", () => {
  for (const text of [
    `](${"](!".repeat(100_000)}`,
    "](a#".repeat(100_000),
    "](a ".repeat(100_000),
  ]) {
    const started = performance.now();

    expect(markdownLinkTargets(text)).toEqual([]);
    expect(performance.now() - started).toBeLessThan(1_000);
  }
});
