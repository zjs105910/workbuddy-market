import type { ChecklistItem } from "./checklist";

export function checklistText(items: readonly ChecklistItem[]): string {
  return items
    .map((item) => {
      const links = item.links.map((link) => `\n     ${link.label}: ${link.url}`).join("");

      return item.done ? `[x] ${item.title}` : `[ ] ${item.title}\n     ${item.action}${links}`;
    })
    .join("\n");
}

export function remainingSteps(items: readonly ChecklistItem[]): readonly ChecklistItem[] {
  return items.filter((item) => !item.done);
}
