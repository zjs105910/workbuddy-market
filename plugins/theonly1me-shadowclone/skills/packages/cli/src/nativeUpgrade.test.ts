import { expect, test } from "bun:test";
import { integrationFixture } from "@shadowclone/core/testing";
import { offerNativeUpgrade } from "./nativeUpgrade";

test("offers a missing native setup once", async () => {
  const fixture = await integrationFixture();
  let questions = 0;
  let setups = 0;

  expect(
    await offerNativeUpgrade({
      paths: fixture.paths,
      ask: () => {
        questions += 1;

        return false;
      },
      setup: () => {
        setups += 1;

        return Promise.resolve();
      },
    }),
  ).toBeFalse();
  expect(
    await offerNativeUpgrade({
      paths: fixture.paths,
      ask: () => {
        questions += 1;

        return true;
      },
      setup: () => {
        setups += 1;

        return Promise.resolve();
      },
    }),
  ).toBeFalse();
  expect(questions).toBe(1);
  expect(setups).toBe(0);
});

test("accepted native setup runs before recording the prompt", async () => {
  const fixture = await integrationFixture();
  let setups = 0;

  expect(
    await offerNativeUpgrade({
      paths: fixture.paths,
      ask: () => true,
      setup: () => {
        setups += 1;

        return Promise.resolve();
      },
    }),
  ).toBeTrue();
  expect(setups).toBe(1);
});
