import { element } from "./dom";
import { nextShootingStar, placeStars, seededRandom, type Star } from "./starGenerator";

const namespace = "http://www.w3.org/2000/svg";

function setProperties(options: { readonly element: SVGElement; readonly properties: Readonly<Record<string, string>> }): void {
  for (const [name, value] of Object.entries(options.properties)) options.element.style.setProperty(name, value);
}

function starElement(star: Star): SVGGElement {
  const group = document.createElementNS(namespace, "g");
  const point = document.createElementNS(namespace, "circle");

  group.setAttribute("class", star.sparkle ? "star sparkle" : "star");
  group.setAttribute("transform", `translate(${star.x.toFixed(1)} ${star.y.toFixed(1)})`);
  point.setAttribute("r", star.radius.toFixed(2));
  setProperties({
    element: group,
    properties: {
      "--brightness": star.brightness.toFixed(2),
      "--twinkle": `${star.twinkleSeconds.toFixed(2)}s`,
      "--delay": `${star.delaySeconds.toFixed(2)}s`,
      "--drift-x": `${star.driftX.toFixed(1)}px`,
      "--drift-y": `${star.driftY.toFixed(1)}px`,
      "--drift": `${star.driftSeconds.toFixed(1)}s`,
    },
  });
  group.append(point);

  if (star.sparkle) {
    const rays = document.createElementNS(namespace, "path");

    rays.setAttribute("d", "M-4 0h8M0 -4v8");
    rays.setAttribute("class", "star-rays");
    group.append(rays);
  }

  return group;
}

export function initializeStarfield(): void {
  const field = element("starfield");
  const random = seededRandom(crypto.getRandomValues(new Uint32Array(1))[0] ?? Date.now());
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const drawn = new Map<number, SVGGElement>();
  let stars: readonly Star[] = [];
  let size = { width: 0, height: 0 };
  let shooting = false;

  const draw = (): void => {
    const bounds = field.getBoundingClientRect();
    const width = Math.max(1, Math.round(bounds.width));
    const height = Math.max(1, Math.round(bounds.height));

    if (width === size.width && height === size.height) return;

    size = { width, height };
    field.setAttribute("viewBox", `0 0 ${width} ${height}`);
    stars = placeStars({ width, height, existing: stars, random });

    const ids = new Set(stars.map((star) => star.id));

    for (const [id, node] of drawn) {
      if (!ids.has(id)) {
        node.remove();
        drawn.delete(id);
      }
    }

    for (const star of stars) {
      if (drawn.has(star.id)) continue;

      const node = starElement(star);

      drawn.set(star.id, node);
      field.append(node);
    }
  };

  const shoot = (): void => {
    const next = shooting ? null : nextShootingStar({ ...size, random, reducedMotion: reducedMotion.matches });

    if (!next) return;

    shooting = true;
    window.setTimeout(() => {
      shooting = false;

      if (!document.hidden && !reducedMotion.matches) {
        const trail = document.createElementNS(namespace, "line");

        trail.setAttribute("class", "shooting-star");
        trail.setAttribute("x2", next.star.travel.toFixed(0));
        trail.setAttribute("transform", `translate(${next.star.x.toFixed(0)} ${next.star.y.toFixed(0)}) rotate(${next.star.angle.toFixed(0)})`);
        setProperties({
          element: trail,
          properties: {
            "--shoot": `${next.star.seconds.toFixed(2)}s`,
            "--length": `${next.star.length.toFixed(0)}px`,
            "--travel": `${next.star.travel.toFixed(0)}px`,
          },
        });
        trail.addEventListener("animationend", () => trail.remove());
        field.append(trail);
      }

      shoot();
    }, next.waitMilliseconds);
  };

  const updateVisibility = (): void => {
    field.classList.toggle("paused", document.hidden);
  };

  document.addEventListener("visibilitychange", updateVisibility);
  reducedMotion.addEventListener("change", shoot);
  new ResizeObserver(draw).observe(field);
  draw();
  updateVisibility();
  shoot();
}
