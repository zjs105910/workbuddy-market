import { describe, expect, test } from "bun:test";
import { parsePersonalInit } from "./initOptions";

describe("parsePersonalInit", () => {
  test("parses read-only status output", () => {
    expect(parsePersonalInit(["--status", "--json"])).toEqual({
      kind: "status",
      json: true,
    });
  });

  test("requires every explicit consent decision", () => {
    expect(() => parsePersonalInit(["--learn"])).toThrow(
      "requires learning, skill maintenance, and background learning decisions",
    );
  });

  test("parses complete positive and negative decisions", () => {
    expect(
      parsePersonalInit([
        "--learn",
        "--no-skill-maintenance",
        "--background-learning",
      ]),
    ).toEqual({
      kind: "consent",
      consent: { learn: true, skills: false, background: true },
    });
  });

  test("rejects background learning without session learning", () => {
    expect(() =>
      parsePersonalInit([
        "--no-learn",
        "--skill-maintenance",
        "--background-learning",
      ]),
    ).toThrow("Background learning requires session learning");
  });

  test("rejects contradictory decisions", () => {
    expect(() =>
      parsePersonalInit([
        "--learn",
        "--no-learn",
        "--skill-maintenance",
        "--no-background-learning",
      ]),
    ).toThrow("Choose either --learn or --no-learn");
  });
});
