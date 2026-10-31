import type { z } from "zod";
import type { checklistSchema } from "@shadowclone/cloud/browser";
import { create } from "./dom";

export function renderChecklist(options: {
  readonly container: HTMLElement;
  readonly checklist: z.infer<typeof checklistSchema>;
}): void {
  const list = create({ tag: "ol", className: "bot-checklist" });

  for (const item of options.checklist) {
    const entry = create({ tag: "li", text: `${item.done ? "Done" : "To do"}: ${item.title}` });

    if (!item.done) {
      entry.append(create({ tag: "p", text: item.action }));

      for (const link of item.links) {
        const anchor = create({ tag: "a", text: link.label });

        anchor.href = link.url;
        anchor.target = "_blank";
        anchor.rel = "noreferrer";
        entry.append(anchor, document.createTextNode(" "));
      }
    }

    list.append(entry);
  }

  options.container.append(list);
}
