import type { VoiceDraft, VoiceProfile } from "../voice/profile";
import { voiceResultSchema, voiceSavedSchema, voiceStatusSchema, type VoiceStatus } from "../voice/protocol";
import { request } from "./api";
import { create, reportError } from "./dom";

const sampleTitles: Readonly<Record<keyof VoiceDraft["samples"], string>> = {
  pullRequest: "Invented pull request",
  reviewComment: "Invented review comment",
  commitMessage: "Invented commit message",
};
const listTitles: Readonly<Record<keyof VoiceProfile, string>> = { traits: "Traits", do: "Do", dont: "Do not" };

export function initializeVoice(): void {
  const dialog = create({ tag: "dialog" });
  const title = create({ tag: "h2", text: "Your writing voice" });
  const intro = create({
    tag: "p",
    text: "Shadowclone can read your own pull requests, review comments, and commit messages through your gh login, and ask your model to describe how you write. You see only that description and invented examples, never your writing itself.",
  });
  const fileNote = create({ tag: "p", className: "voice-file" });
  const consent = create({ tag: "label", className: "voice-consent" });
  const checkbox = create({ tag: "input" });
  const capture = create({ tag: "button", className: "primary-button", text: "Read my writing and describe my voice" });
  const result = create({ tag: "div", className: "voice-result" });
  const status = create({ tag: "p", className: "review-message" });
  const close = create({ tag: "button", className: "quiet-button", text: "Close" });
  let current: VoiceStatus | null = null;
  let draft: VoiceDraft | null = null;
  let edited = false;

  dialog.className = "voice-dialog";
  title.id = "voice-title";
  dialog.setAttribute("aria-labelledby", title.id);
  status.setAttribute("role", "status");
  checkbox.type = "checkbox";
  checkbox.id = "voice-consent";
  consent.append(checkbox, " Let Shadowclone read my GitHub writing for this");
  dialog.append(title, intro, fileNote, consent, capture, result, status, close);
  document.body.append(dialog);

  const run = async (options: { readonly message: string; readonly action: () => Promise<void> }): Promise<void> => {
    status.textContent = options.message;
    dialog.setAttribute("aria-busy", "true");

    try {
      await options.action();
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : "The voice request failed.";
    } finally {
      dialog.setAttribute("aria-busy", "false");
      renderControls();
    }
  };

  const renderControls = (): void => {
    const blocked = current?.voiceFile.state !== "missing";

    checkbox.checked = current?.consent ?? false;
    checkbox.disabled = !current?.allowed;
    capture.disabled = !current?.consent;
    fileNote.textContent = !current
      ? ""
      : !current.allowed
        ? "Your managed policy does not allow Shadowclone to read GitHub writing."
        : blocked
          ? `${current.voiceFile.path} already exists${current.voiceFile.target ? ` as a link to ${current.voiceFile.target}` : ""}. Shadowclone will not change it.`
          : `Saving writes ${current.voiceFile.path}.`;

    for (const button of result.querySelectorAll<HTMLButtonElement>("[data-action=save]")) button.disabled = blocked;
    for (const button of result.querySelectorAll<HTMLButtonElement>("[data-action=rewrite]")) button.disabled = !edited;
  };

  const profileFromInputs = (): VoiceProfile => {
    const values = (key: keyof VoiceProfile) =>
      [...result.querySelectorAll<HTMLInputElement>(`input[data-list=${key}]`)].map((input) => input.value.trim()).filter(Boolean);

    return { traits: values("traits"), do: values("do"), dont: values("dont") };
  };

  const renderDraft = (options: { readonly destination: string; readonly sourceCount?: number }): void => {
    result.replaceChildren();
    edited = false;

    if (!draft) return;

    result.append(
      create({
        tag: "p",
        className: "voice-source",
        text: `Described by ${options.destination}${options.sourceCount ? ` from ${options.sourceCount} pieces of your writing` : ""}. Edit any line, then rewrite the samples.`,
      }),
    );

    for (const key of ["traits", "do", "dont"] as const) {
      const section = create({ tag: "fieldset" });

      section.append(create({ tag: "legend", text: listTitles[key] }));

      for (const value of draft.profile[key]) {
        const input = create({ tag: "input" });

        input.value = value;
        input.dataset.list = key;
        input.setAttribute("aria-label", `${listTitles[key]} line`);
        input.addEventListener("input", () => {
          edited = true;
          renderControls();
        });
        section.append(input);
      }

      result.append(section);
    }

    for (const key of ["pullRequest", "reviewComment", "commitMessage"] as const) {
      result.append(create({ tag: "h3", text: sampleTitles[key] }), create({ tag: "pre", text: draft.samples[key] }));
    }

    const actions = create({ tag: "div", className: "dialog-actions" });
    const discard = create({ tag: "button", className: "quiet-button", text: "Discard" });
    const rewrite = create({ tag: "button", className: "quiet-button", text: "Rewrite the samples" });
    const save = create({ tag: "button", className: "primary-button", text: "Save my voice" });

    rewrite.dataset.action = "rewrite";
    save.dataset.action = "save";
    discard.addEventListener("click", () => {
      draft = null;
      result.replaceChildren();
      status.textContent = "Discarded. Nothing was saved.";
    });
    rewrite.addEventListener("click", () =>
      run({
        message: "Rewriting the samples with your fast model…",
        action: async () => {
          const rewritten = await request({ path: "/api/voice/rewrite", schema: voiceResultSchema, body: { profile: profileFromInputs() } });

          draft = rewritten.draft;
          renderDraft({ destination: rewritten.destination });
          status.textContent = "The samples now follow your edits.";
        },
      }),
    );
    save.addEventListener("click", () =>
      run({
        message: "Saving…",
        action: async () => {
          if (!draft) return;

          const saved = await request({ path: "/api/voice/save", schema: voiceSavedSchema, body: { ...draft, profile: profileFromInputs() } });

          current = await request({ path: "/api/voice/status", schema: voiceStatusSchema, body: {} });
          status.textContent = `Saved ${saved.path}.`;
        },
      }),
    );
    actions.append(discard, rewrite, save);
    result.append(actions);
    renderControls();
  };

  checkbox.addEventListener("change", () =>
    run({
      message: checkbox.checked ? "Saving your consent…" : "Turning reading off…",
      action: async () => {
        current = await request({ path: "/api/voice/consent", schema: voiceStatusSchema, body: { enabled: checkbox.checked } });
        status.textContent = current.consent ? "Shadowclone may read your GitHub writing." : "Reading is off. Collected writing was discarded.";
      },
    }),
  );
  capture.addEventListener("click", () =>
    run({
      message: "Reading your writing and asking your model. This can take a minute…",
      action: async () => {
        const captured = await request({ path: "/api/voice/capture", schema: voiceResultSchema, body: {} });

        draft = captured.draft;
        renderDraft(captured);
        status.textContent = "Review the description and the invented examples.";
      },
    }),
  );
  close.addEventListener("click", () => dialog.close());

  const open = create({ tag: "button", className: "quiet-button", text: "My voice" });

  open.addEventListener("click", () => {
    dialog.showModal();
    run({
      message: "",
      action: async () => {
        current = await request({ path: "/api/voice/status", schema: voiceStatusSchema, body: {} });
      },
    }).catch(reportError);
  });
  document.querySelector(".toolbar")?.append(open);
}
