import type { BrowserItem } from "../protocol";
import { renderConstellationList } from "./constellationList";
import {
  cellsPerRow,
  layoutConstellation,
  type PositionedConstellationLink,
  type PositionedConstellationNode,
} from "./constellationLayout";
import { create, element, svg } from "./dom";
import { hubIcon, skillIcon } from "./icons";
import { skillTitle } from "./presentation";
import { collapsedGroups, drawGroupControls, toggleGroup, updateGroupState } from "./mapGroups";
import { editor, equipped } from "./state";

const namespace = "http://www.w3.org/2000/svg";
let chooseItem: (item: BrowserItem) => void = () => undefined;
let chooseGroup: (items: readonly BrowserItem[]) => void = () => undefined;
let renderedSignature = "";
let itemsById: ReadonlyMap<string, BrowserItem> = new Map();
const skillElements = new Map<string, { readonly node: PositionedConstellationNode; readonly element: SVGGElement }>();
const hubElements = new Map<string, { readonly node: PositionedConstellationNode; readonly element: SVGGElement }>();

function svgElement<Name extends keyof SVGElementTagNameMap>(name: Name): SVGElementTagNameMap[Name] {
  return document.createElementNS(namespace, name);
}

function itemFor(node: PositionedConstellationNode): BrowserItem | undefined {
  const items = node.itemIds
    .map((id) => itemsById.get(id))
    .filter((item): item is BrowserItem => item !== undefined);

  return items.find(equipped) ?? items[0];
}

function groupItems(hubId: string): readonly BrowserItem[] {
  return (editor.view?.constellation.leaves ?? [])
    .filter((leaf) => leaf.parentId === hubId)
    .flatMap((leaf) => {
      const items = leaf.itemIds.map((id) => itemsById.get(id)).filter((item): item is BrowserItem => item !== undefined);
      const item = items.find(equipped) ?? items[0];

      return item ? [item] : [];
    });
}

function nodeTitle(node: PositionedConstellationNode): string {
  const item = itemFor(node);

  return item ? skillTitle(item) : node.title;
}

function matchesSearch(node: PositionedConstellationNode): boolean {
  const item = itemFor(node);

  return (
    !editor.search ||
    `${nodeTitle(node)} ${item?.description ?? ""}`.toLowerCase().includes(editor.search.toLowerCase())
  );
}

function labelLines(title: string): readonly string[] {
  const lines: string[] = [""];

  for (const word of title.split(/\s+/)) {
    const last = lines.at(-1) ?? "";

    if (last && last.length + word.length >= 16) lines.push(word);
    else lines[lines.length - 1] = `${last} ${word}`.trim();
  }

  return lines
    .slice(0, 2)
    .map((line, index) => `${line.slice(0, 17)}${(index === 1 && lines.length > 2) || line.length > 17 ? "…" : ""}`);
}

function drawNode(options: { readonly group: SVGGElement; readonly node: PositionedConstellationNode }): void {
  const { node } = options;
  const item = itemFor(node);
  const container = svgElement("g");
  const size = node.kind === "skill" ? 26 : node.kind === "root" ? 0 : 32;
  const label = svgElement("text");

  container.setAttribute("class", `map-node map-node-${node.kind}`);
  container.setAttribute("transform", `translate(${node.x} ${node.y})`);
  container.dataset.nodeId = node.id;

  if (node.kind === "skill") {
    const hit = svgElement("rect");

    for (const [name, value] of Object.entries({ x: "-26", y: "-26", width: "52", height: "52", class: "map-node-hit" })) {
      hit.setAttribute(name, value);
    }

    container.append(hit);
    container.setAttribute("role", "button");
    container.setAttribute("tabindex", "0");
  }

  if (node.kind === "root") {
    const gem = svgElement("circle");

    gem.setAttribute("r", "26");
    container.append(gem);
  } else {
    const gem = svgElement("rect");

    for (const [name, value] of Object.entries({
      x: String(-size / 2),
      y: String(-size / 2),
      width: String(size),
      height: String(size),
      rx: "6",
      transform: "rotate(45)",
      class: "map-node-gem",
    })) {
      gem.setAttribute(name, value);
    }

    container.append(gem);
  }

  label.setAttribute("text-anchor", "middle");

  for (const [index, line] of labelLines(nodeTitle(node)).entries()) {
    const span = svgElement("tspan");

    span.setAttribute("x", "0");
    span.setAttribute("y", String((node.kind === "skill" ? 34 : 44) + index * 16));
    span.textContent = line;
    label.append(span);
  }

  const title = svgElement("title");

  title.textContent = nodeTitle(node);
  container.append(title, label);

  if (node.kind === "root") {
    const mark = document.querySelector(".brand-mark");

    if (mark instanceof HTMLImageElement) {
      const image = svgElement("image");

      for (const [name, value] of Object.entries({ href: mark.src, x: "-16", y: "-16", width: "32", height: "32" })) {
        image.setAttribute(name, value);
      }

      container.append(image);
    }
  } else {
    const icon = svgElement("foreignObject");
    const iconContainer = create({ tag: "span", className: "map-node-icon" });

    for (const [name, value] of Object.entries({ x: "-9", y: "-9", width: "18", height: "18" })) {
      icon.setAttribute(name, value);
    }

    iconContainer.append(item ? skillIcon(item) : hubIcon(node.title));
    icon.append(iconContainer);
    container.append(icon);
  }

  if (node.kind === "category" || node.kind === "source") {
    drawGroupControls({
      container,
      node,
      toggle: (id) => {
        toggleGroup(id);
        refreshTree();
        document.querySelector<SVGGElement>(`[data-node-id="${CSS.escape(id)}"] .map-collapse`)?.focus();
      },
      equipAll: (id) => chooseGroup(groupItems(id)),
    });
    hubElements.set(node.id, { node, element: container });
  }

  if (node.kind === "skill" && item) {
    const choose = (): void => chooseItem(itemFor(node) ?? item);

    container.addEventListener("click", choose);
    container.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        choose();
      }
    });
    skillElements.set(node.id, { node, element: container });
  }

  options.group.append(container);
}

function linkPath(link: PositionedConstellationLink): string {
  if (!link.sibling) return `M${link.sourceX} ${link.sourceY}L${link.targetX} ${link.targetY}`;

  const middle = (link.sourceX + link.targetX) / 2;

  return `M${link.sourceX} ${link.sourceY - 18}Q${middle} ${link.sourceY - 60} ${link.targetX} ${link.targetY - 18}`;
}

function updateStates(): void {
  for (const { node, element: container } of hubElements.values()) {
    updateGroupState({ element: container, node, items: groupItems(node.id) });
  }

  for (const { node, element: container } of skillElements.values()) {
    const item = itemFor(node);
    const selected = item ? equipped(item) : false;

    container.classList.toggle("equipped", selected);
    container.classList.toggle("active", item?.id === editor.activeId);
    container.classList.toggle("search-miss", !matchesSearch(node));
    container.setAttribute("aria-pressed", String(selected));
    container.setAttribute(
      "aria-label",
      `${nodeTitle(node)}${item?.owner === "provider" ? ", managed by its plugin" : item?.alwaysOn ? ", always on" : selected ? ", equipped" : ""}`,
    );
  }
}

export function renderTree(options: {
  readonly choose: (item: BrowserItem) => void;
  readonly chooseGroup: (items: readonly BrowserItem[]) => void;
}): void {
  chooseItem = options.choose;
  chooseGroup = options.chooseGroup;
  const canvas = svg("constellation-map");
  const view = editor.view;

  if (!view) return;

  renderConstellationList({ constellation: view.constellation, inspect: (id) => {
    const item = view.items.find((candidate) => candidate.id === id);

    if (item) chooseItem(item);
  } });

  const width = canvas.getBoundingClientRect().width;

  if (width <= 0) return;

  itemsById = new Map(view.items.map((item) => [item.id, item]));

  const signature = JSON.stringify([cellsPerRow(width), view.constellation, [...collapsedGroups()]]);

  if (signature !== renderedSignature) {
    const layout = layoutConstellation({ constellation: view.constellation, width, collapsed: collapsedGroups() });
    const group = svgElement("g");

    renderedSignature = signature;
    skillElements.clear();
    hubElements.clear();
    canvas.setAttribute("viewBox", `0 0 ${Math.round(width)} ${Math.round(layout.height)}`);
    canvas.style.height = `${Math.round(layout.height)}px`;
    canvas.replaceChildren(group);

    for (const link of layout.links) {
      const path = svgElement("path");

      path.setAttribute("class", link.sibling ? "map-link sibling" : "map-link");
      path.setAttribute("d", linkPath(link));
      group.append(path);
    }

    for (const node of layout.nodes) drawNode({ group, node });
  }

  updateStates();
}

export function initializeTree(): void {
  const canvas = svg("constellation-map");
  let lastWidth = 0;

  new ResizeObserver(() => {
    const width = canvas.getBoundingClientRect().width;

    if (Math.round(width) !== Math.round(lastWidth)) {
      lastWidth = width;
      renderTree({ choose: chooseItem, chooseGroup });
    }
  }).observe(canvas);

  const toggle = element("toggle-constellation-view");

  toggle.addEventListener("click", () => {
    const listView = element("constellation").classList.toggle("list-view");

    toggle.setAttribute("aria-pressed", String(listView));
  });
}

export function refreshTree(): void {
  renderTree({ choose: chooseItem, chooseGroup });
}
