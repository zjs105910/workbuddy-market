import type { BrowserItem } from "../protocol";
import { create, element, notice } from "./dom";
import { editor, equipped, setEquipped } from "./state";
import { skillSummary, skillTitle } from "./presentation";

function instructionEditor(options: {
  readonly item: BrowserItem;
  readonly rerender: () => void;
}): HTMLDetailsElement {
  const editorPanel = create({ tag: "details", className: "editor" });

  editorPanel.append(create({ tag: "summary", text: "Edit instructions" }));

  const field = create({ tag: "textarea" });

  field.value = editor.input.edits[options.item.id] ?? options.item.text;
  field.maxLength = 48_000;
  field.setAttribute("aria-label", `Instructions for ${options.item.title}`);

  const save = create({
    tag: "button",
    className: "quiet-button",
    text: "Save to draft",
  });

  save.addEventListener("click", () => {
    if (!equipped(options.item)) {
      setEquipped(options.item);
    }

    editor.input.edits[options.item.id] = field.value;
    editor.input.choices[options.item.id] = true;
    editor.dirty = true;

    notice({
      message:
        "Instructions added to your draft. Review the changes before applying.",
      success: true,
    });
    options.rerender();
  });
  editorPanel.append(field, save);

  return editorPanel;
}

export function renderDetail(options: {
  readonly rerender: () => void;
  readonly companion: (item: BrowserItem) => void;
}): void {
  const container = element("detail");
  const item = editor.view?.items.find((entry) => entry.id === editor.activeId);

  container.replaceChildren();

  if (!item) {
    container.append(create({ tag: "h2", text: "Choose a skill." }));
    container.append(
      create({
        tag: "p",
        className: "detail-description",
        text: "Inspect a star to see what it teaches your agent.",
      }),
    );

    return;
  }

  container.append(
    create({
      tag: "p",
      className: "eyebrow",
      text: `${(item.category ?? "CUSTOM").replaceAll("-", " ").toUpperCase()} / ${item.kind.toUpperCase()}`,
    }),
    create({ tag: "h2", text: skillTitle(item) }),
    create({
      tag: "p",
      className: "detail-description",
      text: item.description,
    }),
  );

  const behavior = create({ tag: "div", className: "behavior" });

  behavior.append(
    create({ tag: "p", className: "eyebrow", text: "YOUR AGENT WILL" }),
    create({
      tag: "p",
      text: skillSummary({ item, editedText: editor.input.edits[item.id] }),
    }),
  );
  container.append(behavior);

  const external = item.owner === "provider";
  const locked = editor.view?.locked[item.id] !== undefined;

  container.append(
    create({
      tag: "p",
      className: "skill-status",
      text: item.alwaysOn
        ? "◇ Always on"
        : locked
          ? "◇ Shared requirement"
          : external
            ? "◇ Managed by its provider"
            : "◇ Workflow guidance",
    }),
  );

  if (locked) {
    container.append(
      create({
        tag: "p",
        className: "owner-note",
        text: item.alwaysOn
          ? "Shadowclone always applies this skill. Your agent loads it before it writes any text that a person reads."
          : "This choice belongs to the shared repository build. Switch to shared scope to propose a reviewed change.",
      }),
    );

    return;
  }

  const toggle = create({
    tag: "button",
    className: "primary-button",
    text: external
      ? "Create a local companion"
      : equipped(item)
        ? "Unequip skill"
        : "Equip skill",
  });

  toggle.addEventListener("click", () => {
    if (external) {
      options.companion(item);

      return;
    }

    setEquipped(item);
    options.rerender();
  });
  container.append(toggle);

  if (external) {
    container.append(
      create({
        tag: "p",
        className: "owner-note",
        text: "Enable or disable this package in its harness. A companion adds your own instructions without changing the package.",
      }),
    );
  } else {
    container.append(instructionEditor({ item, rerender: options.rerender }));
  }
}
