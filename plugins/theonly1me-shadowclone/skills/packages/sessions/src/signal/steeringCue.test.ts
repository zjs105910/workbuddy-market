import { expect, test } from "bun:test";
import { hasDurableSteeringCue } from "./steeringCue";

test("durable steering phrases are recognized", () => {
  for (const text of [
    "Never add default exports.",
    "Always run the gate before presenting.",
    "No, keep the existing parser.",
    "Actually, use the options object instead.",
    "Don't touch the migrations folder.",
    "From now on, write tests first.",
  ]) {
    expect(hasDurableSteeringCue(text)).toBeTrue();
  }
});

test("acknowledgements and task requests carry no durable steering", () => {
  for (const text of [
    "Thanks, that looks good. Continue with the next file.",
    "Add a status filter to the list command.",
    "What does this function return?",
    "Yes, go ahead.",
  ]) {
    expect(hasDurableSteeringCue(text)).toBeFalse();
  }
});
