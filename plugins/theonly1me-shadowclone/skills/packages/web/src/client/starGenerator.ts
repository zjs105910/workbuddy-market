export type Star = {
  readonly id: number;
  readonly x: number;
  readonly y: number;
  readonly radius: number;
  readonly brightness: number;
  readonly twinkleSeconds: number;
  readonly delaySeconds: number;
  readonly driftX: number;
  readonly driftY: number;
  readonly driftSeconds: number;
  readonly sparkle: boolean;
};

export type ShootingStar = {
  readonly x: number;
  readonly y: number;
  readonly angle: number;
  readonly length: number;
  readonly travel: number;
  readonly seconds: number;
};

export const starDensity = { squarePixelsPerStar: 9_000, maximumStars: 600, attemptsPerStar: 30 } as const;

export function seededRandom(seed: number): () => number {
  let state = seed >>> 0;

  return () => {
    state = (state + 0x6d2b79f5) >>> 0;

    let value = Math.imul(state ^ (state >>> 15), state | 1);

    value ^= value + Math.imul(value ^ (value >>> 7), value | 61);

    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

export function starCount(options: { readonly width: number; readonly height: number }): number {
  return Math.min(
    starDensity.maximumStars,
    Math.round((Math.max(0, options.width) * Math.max(0, options.height)) / starDensity.squarePixelsPerStar),
  );
}

export function minimumStarDistance(options: { readonly width: number; readonly height: number }): number {
  const count = Math.max(1, starCount(options));

  return Math.sqrt((options.width * options.height) / count) * 0.55;
}

function between(options: { readonly random: () => number; readonly low: number; readonly high: number }): number {
  return options.low + options.random() * (options.high - options.low);
}

function newStar(options: { readonly id: number; readonly x: number; readonly y: number; readonly random: () => number }): Star {
  const { random } = options;
  const sparkle = random() < 0.08;
  const angle = random() * Math.PI * 2;
  const distance = between({ random, low: 4, high: 14 });

  return {
    id: options.id,
    x: options.x,
    y: options.y,
    radius: sparkle ? between({ random, low: 1.4, high: 1.9 }) : between({ random, low: 0.5, high: 1.2 }),
    brightness: between({ random, low: 0.35, high: 1 }),
    twinkleSeconds: between({ random, low: 3.5, high: 14 }),
    delaySeconds: -between({ random, low: 0, high: 14 }),
    driftX: Math.cos(angle) * distance,
    driftY: Math.sin(angle) * distance,
    driftSeconds: between({ random, low: 18, high: 60 }),
    sparkle,
  };
}

export function placeStars(options: {
  readonly width: number;
  readonly height: number;
  readonly existing: readonly Star[];
  readonly random: () => number;
}): readonly Star[] {
  const target = starCount(options);
  const minimum = minimumStarDistance(options);
  const kept = options.existing
    .filter((star) => star.x >= 0 && star.x <= options.width && star.y >= 0 && star.y <= options.height)
    .slice(0, target);
  const stars: Star[] = [...kept];
  const cellSize = minimum / Math.SQRT2;
  const grid = new Map<string, Star>();
  const cellKey = (options: { readonly x: number; readonly y: number }) =>
    `${Math.floor(options.x / cellSize)}:${Math.floor(options.y / cellSize)}`;
  const crowded = (point: { readonly x: number; readonly y: number }): boolean => {
    const column = Math.floor(point.x / cellSize);
    const row = Math.floor(point.y / cellSize);

    for (let columnOffset = -2; columnOffset <= 2; columnOffset += 1) {
      for (let rowOffset = -2; rowOffset <= 2; rowOffset += 1) {
        const neighbor = grid.get(`${column + columnOffset}:${row + rowOffset}`);

        if (neighbor && Math.hypot(neighbor.x - point.x, neighbor.y - point.y) < minimum) return true;
      }
    }

    return false;
  };
  let nextId = Math.max(0, ...stars.map((star) => star.id + 1));

  for (const star of kept) grid.set(cellKey(star), star);

  for (let attempts = 0; stars.length < target && attempts < target * starDensity.attemptsPerStar; attempts += 1) {
    const point = { x: options.random() * options.width, y: options.random() * options.height };

    if (crowded(point)) continue;

    const star = newStar({ id: nextId, ...point, random: options.random });

    nextId += 1;
    stars.push(star);
    grid.set(cellKey(star), star);
  }

  return stars;
}

export function nextShootingStar(options: {
  readonly width: number;
  readonly height: number;
  readonly random: () => number;
  readonly reducedMotion: boolean;
}): { readonly star: ShootingStar; readonly waitMilliseconds: number } | null {
  if (options.reducedMotion || options.width <= 0 || options.height <= 0) return null;

  const { random } = options;

  return {
    waitMilliseconds: between({ random, low: 9_000, high: 28_000 }),
    star: {
      x: between({ random, low: options.width * 0.1, high: options.width * 0.9 }),
      y: between({ random, low: 0, high: Math.min(options.height * 0.5, 600) }),
      angle: random() < 0.5 ? between({ random, low: 20, high: 40 }) : between({ random, low: 140, high: 160 }),
      length: between({ random, low: 70, high: 140 }),
      travel: between({ random, low: 220, high: 380 }),
      seconds: between({ random, low: 0.7, high: 1.3 }),
    },
  };
}
