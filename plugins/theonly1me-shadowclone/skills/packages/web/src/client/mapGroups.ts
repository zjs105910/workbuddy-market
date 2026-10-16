import type { BrowserItem } from "../protocol";
import type { PositionedConstellationNode } from "./constellationLayout";
import { equippableItems, equipped } from "./state";

const namespace = "http://www.w3.org/2000/svg";
const storageKey = "shadowclone-collapsed-groups";

function readCollapsed(): Set<string> {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(storageKey) ?? "[]");

    return new Set(Array.isArray(parsed) ? parsed.filter((value): value is string => typeof value === "string") : []);
  } catch {
    return new Set();
  }
}

let collapsed = readCollapsed();

export function collapsedGroups(): ReadonlySet<string> {
  return collapsed;
}

export function toggleGroup(id: string): void {
  collapsed = new Set(collapsed);

  if (!collapsed.delete(id)) collapsed.add(id);

  try {
    localStorage.setItem(storageKey, JSON.stringify([...collapsed]));
  } catch {
    return;
  }
}

function svgElement<Name extends keyof SVGElementTagNameMap>(name: Name): SVGElementTagNameMap[Name] {
  return document.createElementNS(namespace, name);
}

function onActivate(options: { readonly target: SVGGElement; readonly action: () => void }): void {
  options.target.addEventListener("click", (event) => {
    event.stopPropagation();
    options.action();
  });
  options.target.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      event.stopPropagation();
      options.action();
    }
  });
}

export function drawGroupControls(options: {
  readonly container: SVGGElement;
  readonly node: PositionedConstellationNode;
  readonly toggle: (id: string) => void;
  readonly equipAll: (id: string) => void;
}): void {
  const { container, node } = options;
  const expanded = !collapsed.has(node.id);
  const chevron = svgElement("g");
  const hit = svgElement("circle");
  const mark = svgElement("path");

  chevron.setAttribute("class", "map-collapse");
  chevron.setAttribute("transform", "translate(36 0)");
  chevron.setAttribute("role", "button");
  chevron.setAttribute("tabindex", "0");
  chevron.setAttribute("aria-expanded", String(expanded));
  chevron.setAttribute("aria-label", `${expanded ? "Collapse" : "Expand"} ${node.title}`);
  hit.setAttribute("r", "12");
  mark.setAttribute("d", expanded ? "M2 -4L-2 0L2 4" : "M-2 -4L2 0L-2 4");
  chevron.append(hit, mark);
  onActivate({ target: chevron, action: () => options.toggle(node.id) });
  container.append(chevron);

  if (node.hidden > 0) {
    const count = svgElement("text");

    count.setAttribute("class", "map-hidden-count");
    count.setAttribute("x", "54");
    count.setAttribute("y", "4");
    count.textContent = `${node.hidden} hidden`;
    container.append(count);
  }

  if (node.kind !== "category") return;

  const target = svgElement("rect");

  for (const [name, value] of Object.entries({ x: "-26", y: "-26", width: "52", height: "52", class: "map-node-hit" })) {
    target.setAttribute(name, value);
  }

  container.prepend(target);
  container.setAttribute("role", "button");
  container.setAttribute("tabindex", "0");
  onActivate({ target: container, action: () => options.equipAll(node.id) });
}

export function updateGroupState(options: {
  readonly element: SVGGElement;
  readonly node: PositionedConstellationNode;
  readonly items: readonly BrowserItem[];
}): void {
  if (options.node.kind !== "category") return;

  const open = equippableItems(options.items);
  const all = open.length > 0 && open.every(equipped);

  options.element.classList.toggle("equipped", all);
  options.element.classList.toggle("partial", !all && open.some(equipped));
  options.element.setAttribute("aria-pressed", String(all));
  options.element.setAttribute("aria-disabled", String(open.length === 0));
  options.element.setAttribute(
    "aria-label",
    open.length === 0
      ? `${options.node.title}, managed by plugins`
      : `${all ? "Unequip" : "Equip"} all ${open.length} skills in ${options.node.title}`,
  );
}
