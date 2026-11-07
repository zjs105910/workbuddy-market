import { expect, test } from "bun:test";
import path from "node:path";
import { minimumStarDistance, nextShootingStar, placeStars, seededRandom, starCount, type Star } from "./starGenerator";

function closestPair(stars: readonly Star[]): number {
  let closest = Number.POSITIVE_INFINITY;

  for (const [index, left] of stars.entries()) {
    for (const right of stars.slice(index + 1)) {
      closest = Math.min(closest, Math.hypot(left.x - right.x, left.y - right.y));
    }
  }

  return closest;
}

function place(options: { readonly seed: number; readonly width: number; readonly height: number; readonly existing?: readonly Star[] }) {
  return placeStars({ width: options.width, height: options.height, existing: options.existing ?? [], random: seededRandom(options.seed) });
}

test("stars keep their minimum spacing and stay inside the field", () => {
  for (const seed of [1, 2, 3, 99, 4096]) {
    const stars = place({ seed, width: 1200, height: 900 });

    expect(stars).toHaveLength(starCount({ width: 1200, height: 900 }));
    expect(closestPair(stars)).toBeGreaterThanOrEqual(minimumStarDistance({ width: 1200, height: 900 }));
    expect(stars.every((star) => star.x >= 0 && star.x <= 1200 && star.y >= 0 && star.y <= 900)).toBeTrue();
  }
});

test("the star count scales with the area, up to a cap", () => {
  expect(starCount({ width: 1200, height: 900 })).toBe(120);
  expect(starCount({ width: 1200, height: 1800 })).toBe(240);
  expect(starCount({ width: 4000, height: 9000 })).toBe(600);
});

test("each seed gives a different sky, and one seed gives the same sky", () => {
  const first = place({ seed: 11, width: 1200, height: 900 });
  const second = place({ seed: 12, width: 1200, height: 900 });

  expect(place({ seed: 11, width: 1200, height: 900 })).toEqual(first);
  expect(first.filter((star, index) => star.x === second[index]?.x && star.y === second[index]?.y)).toEqual([]);
  expect(new Set(first.map((star) => star.twinkleSeconds.toFixed(2))).size).toBeGreaterThan(first.length * 0.9);
});

test("a resize keeps the stars that still fit and adds stars for the new area", () => {
  const before = place({ seed: 5, width: 1200, height: 900 });
  const taller = place({ seed: 6, width: 1200, height: 1800, existing: before });
  const narrower = place({ seed: 7, width: 600, height: 900, existing: before });

  expect(taller.slice(0, before.length)).toEqual([...before]);
  expect(taller).toHaveLength(240);
  expect(narrower.every((star) => before.includes(star) && star.x <= 600)).toBeTrue();
  expect(narrower).toHaveLength(starCount({ width: 600, height: 900 }));
});

test("reduced motion stops shooting stars and the CSS stops every star animation", async () => {
  const random = seededRandom(3);

  expect(nextShootingStar({ width: 1200, height: 900, random, reducedMotion: true })).toBeNull();
  expect(nextShootingStar({ width: 1200, height: 900, random, reducedMotion: false })).not.toBeNull();

  const css = await Bun.file(path.join(import.meta.dir, "starfield.css")).text();
  const reduced = css.slice(css.indexOf("@media (prefers-reduced-motion: reduce)"));

  expect(reduced).toContain(".star {\n    animation: none;");
  expect(reduced).toContain("translate: none;");
  expect(reduced).toContain(".shooting-star {\n    display: none;");
});
