import { buildNameResultSchema } from "../buildNameProtocol";
import { request } from "./api";
import { createBuildNamer, type NamerState } from "./buildNamer";
import { create, element } from "./dom";
import { editor, equipped } from "./state";

const namingSetting = "shadowclone-build-naming";

function namingEnabled(): boolean {
  try {
    return localStorage.getItem(namingSetting) !== "off";
  } catch {
    return true;
  }
}

function saveNamingEnabled(enabled: boolean): void {
  try {
    if (enabled) localStorage.removeItem(namingSetting);
    else localStorage.setItem(namingSetting, "off");
  } catch {
    return;
  }
}

const descriptions: Record<Exclude<NamerState["status"], "ready" | "failed">, string> = {
  empty: "Choose the instincts you want your agent to bring to work.",
  off: "Build naming is off. Turn it on to name your build with your fast model.",
  unnamed: "Name this build now, or change a skill and it gets a name 5 seconds later.",
  waiting: "Your build gets a name 5 seconds after your last change.",
  loading: "Naming your build…",
};

function renderName(state: NamerState): void {
  const sheet = element("identity");
  const abilities = element("abilities");
  const tradeoff = element("tradeoff");
  const ready = state.status === "ready" ? state.result : null;

  sheet.dataset.naming = state.status;
  sheet.setAttribute("aria-busy", String(state.status === "loading"));
  element("identity-title").textContent = ready?.name.title ?? "An open canvas";
  element("identity-description").textContent =
    state.status === "ready" ? state.result.name.profile : state.status === "failed" ? state.error : descriptions[state.status];
  abilities.replaceChildren(
    ...(ready?.name.abilities ?? []).map((ability) => {
      const entry = create({ tag: "li" });

      entry.append(create({ tag: "strong", text: ability.skill }), create({ tag: "span", text: ability.text }));

      return entry;
    }),
  );
  tradeoff.hidden = !ready;
  tradeoff.textContent = ready ? `Tradeoff: ${ready.name.tradeoff}` : "";
  element("naming-source").textContent = ready ? `Named by ${ready.destination}` : "";

  const retry = element("retry-name");

  retry.hidden = state.status !== "failed" && state.status !== "unnamed";
  retry.textContent = state.status === "unnamed" ? "Name my build" : "Retry";

  const toggle = element("toggle-naming");

  toggle.textContent = state.status === "off" ? "Turn naming on" : "Turn naming off";
  toggle.setAttribute("aria-pressed", String(state.status !== "off"));
}

const namer = createBuildNamer({
  schedule: ({ run, delayMilliseconds }) => window.setTimeout(run, delayMilliseconds),
  cancel: (handle) => window.clearTimeout(handle),
  fetchName: ({ input, signal }) => request({ path: "/api/build-name", schema: buildNameResultSchema, body: input, signal }),
  onChange: renderName,
});

function selectedItems() {
  return editor.view?.items.filter((item) => item.owner !== "provider" && !item.alwaysOn && equipped(item)) ?? [];
}

function updateName(): void {
  const selected = selectedItems();

  namer.update({
    key: selected.length
      ? JSON.stringify([editor.input.scope, selected.map((item) => item.id).sort(), editor.input.custom])
      : null,
    input: editor.input,
    enabled: namingEnabled(),
    changed: editor.dirty,
  });
}

export function initializeIdentity(): void {
  element("retry-name").addEventListener("click", () => namer.retry());
  element("toggle-naming").addEventListener("click", () => {
    saveNamingEnabled(!namingEnabled());
    updateName();
  });
  renderName(namer.state());
}

export function renderIdentity(): void {
  const selected = selectedItems();

  element("equipped-count").textContent =
    `${selected.length} ${selected.length === 1 ? "skill" : "skills"} equipped${editor.dirty ? " · unsaved changes" : ""}`;
  updateName();

  const requirements = element("requirements");
  requirements.replaceChildren();
  requirements.hidden = !editor.view?.requirements.length;

  if (editor.view?.requirements.length) {
    requirements.append(
      create({ tag: "h3", text: "◇ Repository requirements" }),
    );

    for (const requirement of editor.view.requirements) {
      requirements.append(create({ tag: "p", text: requirement }));
    }
  }
}
