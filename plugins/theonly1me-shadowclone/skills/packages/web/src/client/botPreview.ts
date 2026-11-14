import type { z } from "zod";
import { manifestViewSchema, type setupPreviewSchema } from "@shadowclone/cloud/browser";
import { request } from "./api";
import { create } from "./dom";
import { botButton } from "./botControls";

type Preview = z.infer<typeof setupPreviewSchema>;

export function showBotPreview(options: {
  readonly container: HTMLElement;
  readonly status: HTMLElement;
  readonly preview: Preview;
}) {
  const { container, status, preview } = options;

  container.replaceChildren();
  container.append(
    create({
      tag: "p",
      text:
        `Repository: ${preview.repository} (ID ${preview.repositoryId}). ` +
        `App owner: ${preview.appOwner}. Requester: ${preview.owner}. ` +
        `Skills and rules: ${preview.bytes} bytes.`,
    }),
  );
  container.append(
    create({
      tag: "p",
      text:
        "Review every file below. Approval pushes these files to your private " +
        "shadowclone-skills repository, which the bot reads with a read-only key. It " +
        "also adds a ruleset so only people with write access can update the default " +
        "branch. You add the Claude token on GitHub later. The default-branch workflow " +
        "and code executed with credentials remain trusted.",
    }),
  );

  for (const file of preview.files) {
    const details = create({ tag: "details" });
    const bytes = Uint8Array.from(atob(file.content), (character) => character.charCodeAt(0));

    let text: string;

    try {
      text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
    } catch {
      text = `Binary resource (${bytes.length} bytes), shown as base64:\n${file.content}`;
    }

    details.append(create({ tag: "summary", text: file.path }), create({ tag: "pre", text }));
    container.append(details);
  }

  const approved = create({ tag: "input" });
  const consent = create({ tag: "label", className: "bot-consent" });

  approved.type = "checkbox";
  consent.append(
    approved,
    document.createTextNode("I reviewed the exact guidance and authorize its cloud use."),
  );
  container.append(consent);
  container.append(
    botButton({
      text: "Approve guidance and register my GitHub App",
      status,
      action: async () => {
        if (!approved.checked) {
          throw new Error("Review the files and select the approval checkbox.");
        }

        const view = await request({
          path: "/api/bot/manifest",
          body: { previewId: preview.id },
          schema: manifestViewSchema,
        });
        const form = create({ tag: "form" });
        const manifest = create({ tag: "input" });

        form.action = view.action;
        form.method = "post";
        manifest.type = "hidden";
        manifest.name = "manifest";
        manifest.value = view.manifest;
        form.append(manifest);
        container.append(form);
        form.submit();
      },
    }),
  );
  status.textContent = "Review the selected guidance before continuing.";
}
