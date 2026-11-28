import { withCustomSkill } from "@shadowclone/builds/browser";
import type { BrowserItem } from "../protocol";
import { dialog, element, input, textarea } from "./dom";
import { editor } from "./state";
import { customSkillSchema } from "@shadowclone/environment/browser";

export function openCustomEditor(item?: BrowserItem): void {
  element("custom-status").textContent = "";
  input("custom-name").value = item ? `my-${item.name}`.slice(0, 48) : "";
  input("custom-description").value = item
    ? `Use alongside ${item.name} for my working preferences.`
    : "";
  textarea("custom-body").value = item
    ? `# Personal guidance for ${item.title}\n\n`
    : "";

  dialog("custom-dialog").showModal();
}

export function saveCustomSkill(): void {
  const skill = customSkillSchema.parse({
    name: input("custom-name").value,
    description: input("custom-description").value,
    body: textarea("custom-body").value,
  });
  const id = `custom:${skill.name}`;

  if (editor.view?.items.some((item) => item.name === skill.name)) {
    throw new Error("Choose a name that does not replace an existing skill.");
  }

  editor.input.custom.push(skill);
  editor.input.choices[id] = true;
  editor.dirty = true;
  editor.activeId = id;
  editor.view?.items.push({
    id,
    name: skill.name,
    title: skill.name.replaceAll("-", " "),
    description: skill.description,
    text: `---\nname: ${skill.name}\ndescription: ${JSON.stringify(skill.description)}\n---\n\n${skill.body}\n`,
    kind: "skill",
    category: null,
    section: null,
    axis: null,
    alwaysOn: false,
    owner: "managed",
  });

  if (editor.view) {
    editor.view.constellation = withCustomSkill({
      constellation: editor.view.constellation,
      item: { id, name: skill.name, title: skill.name.replaceAll("-", " "), description: skill.description, category: null },
    });
  }

  dialog("custom-dialog").close();
  input("custom-name").value = "";
  textarea("custom-body").value = "";
}
