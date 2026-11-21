import { expect, test } from "bun:test";
import { invented } from "./fixtures";
import { assertInvented, copiedPassage, voiceDocument } from "./profile";

const source = "The index step threw away every cursor when one file failed to parse, so the next run started over.";

test("a passage of 8 copied words is found, regardless of case and punctuation", () => {
  expect(copiedPassage({ text: "Note: THE INDEX STEP threw away every cursor, when one file broke.", sources: [source] })).toBe(
    "the index step threw away every cursor when",
  );
});

test("7 copied words in a row are allowed", () => {
  expect(copiedPassage({ text: "The index step threw away every cursor today.", sources: [source] })).toBeNull();
});

test("a sample that copies the source is rejected, and an invented one passes", () => {
  expect(() =>
    assertInvented({
      draft: { samples: { ...invented.samples, reviewComment: `Why did ${source.toLowerCase()}` } },
      sources: [source],
    }),
  ).toThrow("The model copied 8 or more words in a row from your writing");
  expect(() => assertInvented({ draft: invented, sources: [source] })).not.toThrow();
});

test("the voice file lists the profile and labels the examples as invented", () => {
  const document = voiceDocument(invented);

  expect(document).toStartWith("# My writing voice\n");
  expect(document).toContain("The examples are invented.");
  expect(document).toContain("## Do not\n\n- Sell the change\n- Narrate the investigation");
  expect(document).toContain("### Commit message\n\nfix: keep the saved city after a refresh\n");
});
