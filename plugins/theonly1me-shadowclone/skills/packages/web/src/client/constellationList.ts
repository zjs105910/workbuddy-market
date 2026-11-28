import type { Constellation } from "@shadowclone/builds/browser";
import type { BrowserItem } from "../protocol";
import { create, element } from "./dom";
import { skillTitle } from "./presentation";
import { editor, equipped } from "./state";

function itemFor(itemIds: readonly string[]): BrowserItem | undefined {
  const items = itemIds
    .map((id) => editor.view?.items.find((item) => item.id === id))
    .filter((item): item is BrowserItem => item !== undefined);

  return items.find(equipped) ?? items[0];
}

function matches(item: BrowserItem): boolean {
  return `${skillTitle(item)} ${item.description}`
    .toLowerCase()
    .includes(editor.search.toLowerCase());
}

export function renderConstellationList(options: {
  readonly constellation: Constellation;
  readonly inspect: (id: string) => void;
}): void {
  const list = element("constellation-list");
  list.replaceChildren();
  const parents = new Map(options.constellation.hubs.map((hub) => [hub.id, hub.parentId]));

  for (const hub of options.constellation.hubs.filter(
    (entry) => entry.parentId === null,
  )) {
    const section = create({ tag: "section", className: "skill-list-group" });
    section.append(create({ tag: "h3", text: hub.title }));
    for (const leaf of options.constellation.leaves.filter((entry) => {
      let parent: string | null = entry.parentId;
      while (parent) {
        if (parent === hub.id) return true;
        parent = parents.get(parent) ?? null;
      }
      return false;
    })) {
      const item = itemFor(leaf.itemIds);

      if (!item || !matches(item)) continue;
      const button = create({
        tag: "button",
        className: "skill-list-item",
        text: skillTitle(item),
      });
      button.classList.toggle("equipped", equipped(item));
      button.addEventListener("click", () => options.inspect(item.id));
      section.append(button);
    }

    if (section.childElementCount > 1) list.append(section);
  }
}
