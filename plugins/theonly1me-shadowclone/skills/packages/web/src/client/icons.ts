import type { BrowserItem } from "../protocol";

const shapes = {
  modules: "M4 4h6v6H4ZM14 4h6v6h-6ZM4 14h6v6H4ZM14 14h6v6h-6Z",
  code: "m8 5-6 7 6 7m8-14 6 7-6 7m-3-16-2 18",
  focus: "M8 3H4v4m12-4h4v4M4 17v4h4m12-4v4h-4M8 9h8v6H8Z",
  bug: "M9 5 7 2m8 3 2-3M8 9V7a4 4 0 0 1 8 0v2M6 9h12v6a6 6 0 0 1-12 0Zm6 0v12M2 10h4m12 0h4M2 15h4m12 0h4M4 21l3-3m10 0 3 3",
  flask: "M9 3h6m-5 0v7l-6 9q-1 2 2 2h12q3 0 2-2l-6-9V3M7 15h10",
  check: "m2 12 5 5L19 5M12 17l10-10",
  route:
    "M7 5h10a3 3 0 0 1 0 6H7a3 3 0 0 0 0 6h10M7 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6m10 12a3 3 0 1 0 0 6 3 3 0 0 0 0-6",
  compass: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m-3 7 8-2-2 8-8 2Z",
  flag: "M5 22V3q4-3 8 0t7 0v10q-3 3-7 0t-8 0",
  merge: "M6 2v8q0 5 6 5h6m-4-4 4 4-4 4M6 18v4M18 2v5",
  layers: "m12 2 10 6-10 6L2 8Zm-9 11 9 5 9-5M3 17l9 5 9-5",
  link: "m9 15 6-6m-7 4-2 2a4 4 0 0 0 6 6l3-3m1-5 2-2a4 4 0 0 0-6-6L9 8",
  shield: "m12 2 8 3v7q0 6-8 10-8-4-8-10V5Zm-4 9 3 3 5-6",
  question:
    "M8 7a4 4 0 1 1 6 4q-2 1-2 4m0 4v1M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20",
  spark: "m12 2 3 7 7 3-7 3-3 7-3-7-7-3 7-3Z",
  search: "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14m5 12 6 6",
};

const skillIcons: Readonly<Record<string, keyof typeof shapes>> = {
  "design-deep-modules": "modules",
  "typescript-type-safety": "code",
  "scope-confirmed-changes": "focus",
  "choose-by-consequence": "compass",
  "write-plain-english": "spark",
  "plan-with-review-page": "route",
  "verify-review-findings": "search",
  "refactor-boundaries": "layers",
  "refactor-preserve": "shield",
  "dependencies-existing": "link",
  "dependencies-mature": "layers",
  "diagnose-before-editing": "bug",
  "tests-that-catch-bugs": "flask",
  "research-primary-sources": "search",
  "verify-and-review": "check",
  "planning-first": "route",
  "planning-when-costly": "compass",
  "questions-autonomous": "flag",
  "questions-early": "question",
  "resolve-conflicts-by-intent": "merge",
};

function shapeIcon(shape: keyof typeof shapes): SVGSVGElement {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");

  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", "1.25");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  path.setAttribute("d", shapes[shape]);
  svg.append(path);

  return svg;
}

export function skillIcon(item: BrowserItem): SVGSVGElement {
  return shapeIcon(skillIcons[item.id] ?? "spark");
}

export function hubIcon(title: string): SVGSVGElement {
  const category = title.toLowerCase();
  const categories: Readonly<Record<string, keyof typeof shapes>> = {
    engineering: "code", architecture: "modules", typescript: "code", workflow: "route",
    dependenc: "layers", testing: "flask", communication: "question", debugging: "bug",
    planning: "compass", research: "search", review: "check", setup: "spark",
  };
  const shape = Object.entries(categories).find(([name]) => category.includes(name))?.[1] ?? "compass";
  return shapeIcon(shape);
}
