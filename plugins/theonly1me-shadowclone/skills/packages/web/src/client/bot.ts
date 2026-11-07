import { setupPreviewSchema, setupStateSchema } from "@shadowclone/cloud/browser";
import { request } from "./api";
import { create } from "./dom";
import { showAccountSetup } from "./botAccount";
import { renderChecklist } from "./botChecklist";
import { botButton, botField } from "./botControls";
import { showBotPreview } from "./botPreview";

export function initializeBotSetup(): void {
  const dialog = create({ tag: "dialog" });
  dialog.className = "bot-dialog";
  const title = create({ tag: "h2", text: "Your Shadowclone cloud bot" });
  const content = create({ tag: "div" });
  const status = create({ tag: "p" });
  const close = create({ tag: "button", className: "quiet-button", text: "Close" });

  title.id = "bot-title";
  dialog.setAttribute("aria-labelledby", title.id);
  status.setAttribute("role", "status");
  close.addEventListener("click", () => dialog.close());
  dialog.append(title, content, status, close);
  document.body.append(dialog);

  let showAccount = true;

  async function load(): Promise<void> {
    const state = await request({ path: "/api/bot/state", schema: setupStateSchema });

    content.replaceChildren();

    if (state.checklist) {
      renderChecklist({ container: content, checklist: state.checklist });
      status.textContent = "Add the Claude token on GitHub, then merge the setup pull request.";
      return;
    }

    if (state.app) {
      const install = create({ tag: "a", text: `Install ${state.app.name} on GitHub` });
      const previewId = state.previewId;

      install.href = state.app.installUrl;
      install.target = "_blank";
      install.rel = "noreferrer";
      content.append(
        install,
        create({
          tag: "p",
          text:
            `Choose Only select repositories. Include ${state.repository}. ` +
            "Return to this tab after installation. All repositories is rejected.",
        }),
        create({
          tag: "p",
          text: "After the setup, you add the Claude token on the environment page that the checklist links to.",
        }),
        botButton({
          text: "Verify installation and create the setup PR",
          status,
          action: async () => {
            if (!previewId) {
              throw new Error("Start a fresh setup and review the guidance again.");
            }

            await request({ path: "/api/bot/activate", body: { previewId }, schema: setupStateSchema });
            await load();
          },
        }),
      );
      status.textContent = "GitHub controls account and organization installation approval.";
      return;
    }

    const initialRepository = new URLSearchParams(location.search).get("repository") ?? state.repository ?? "";

    if (showAccount) {
      showAccountSetup({
        container: content,
        status,
        repository: initialRepository,
        onApp: () => {
          showAccount = false;
          load().catch((error: unknown) => {
            status.textContent = error instanceof Error ? error.message : "Setup failed.";
          });
        },
      });
      status.textContent = "Start in this repository checkout with gh auth login and an active Shadowclone skills environment.";
      return;
    }

    const repository = botField({
      label: "Repository (owner/repository)",
      value: initialRepository,
    });
    const name = botField({ label: "Clone name", value: "my-shadowclone" });
    const skills = botField({
      label: "Selected skill names, separated by commas",
      value: state.skills.length ? state.skills.join(", ") : "shadowclone-work",
    });

    content.append(
      create({
        tag: "p",
        text:
          "Create a GitHub App that you own and name. Only selected repositories " +
          "receive access. Owner issues start work; @shadowclone requests changes. You " +
          "review and merge each PR.",
      }),
      repository.label,
      name.label,
      skills.label,
      botButton({
        text: "Preview the exact guidance",
        status,
        action: async () => {
          const preview = await request({
            path: "/api/bot/preview",
            schema: setupPreviewSchema,
            body: {
              repository: repository.input.value.trim(),
              name: name.input.value.trim(),
              skills: skills.input.value
                .split(",")
                .map((value) => value.trim())
                .filter(Boolean),
            },
          });

          showBotPreview({ container: content, status, preview });
        },
      }),
    );
    status.textContent =
      "Start in this repository checkout with gh auth login and an active " +
      "Shadowclone skills environment.";
  }

  const button = botButton({
    text: "GitHub clone",
    status,
    action: async () => {
      dialog.showModal();
      await load();
    },
  });

  document.querySelector(".toolbar")?.append(button);

  if (new URLSearchParams(location.search).get("bot") === "github") {
    button.click();
  }
}
