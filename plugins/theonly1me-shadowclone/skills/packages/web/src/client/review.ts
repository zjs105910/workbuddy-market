import {
  applyResultSchema,
  previewSchema,
  type BuildPreview,
} from "../protocol";
import { request } from "./api";
import { create, dialog, element, notice } from "./dom";
import { editor } from "./state";

let reviewed: BuildPreview | null = null;

export async function reviewChanges(): Promise<void> {
  if (editor.view === null) {
    throw new Error("Wait for your skills to load before reviewing the build.");
  }
  const preview = await request({
    path: "/api/preview",
    schema: previewSchema,
    body: editor.input,
  });

  reviewed = preview;

  const content = element("review-content");

  content.replaceChildren();
  content.append(
    create({
      tag: "p",
      className: "review-message",
      text: `${preview.changes.length} local files will change. Review the instructions and destinations below.`,
    }),
  );

  for (const warning of preview.warnings) {
    content.append(
      create({ tag: "p", className: "review-warning", text: warning }),
    );
  }

  for (const change of preview.changes) {
    const detail = create({ tag: "details", className: "file-change" });

    detail.append(create({ tag: "summary", text: change.path }));

    if (change.internal) {
      detail.append(
        create({
          tag: "p",
          text: "Local configuration or supporting resource. Its previous version is retained for undo.",
        }),
      );
    } else {
      detail.append(
        create({ tag: "h4", text: "Before" }),
        create({ tag: "pre", text: change.before ?? "New file" }),
        create({ tag: "h4", text: "After" }),
        create({ tag: "pre", text: change.after ?? "Remove managed file" }),
      );
    }

    content.append(detail);
  }

  dialog("review-dialog").showModal();
}

export async function applyReviewedBuild(): Promise<void> {
  if (reviewed === null) {
    throw new Error("Review your build before applying it.");
  }

  await request({
    path: "/api/apply",
    schema: applyResultSchema,
    body: { previewId: reviewed.id },
  });
  reviewed = null;
  dialog("review-dialog").close();

  notice({
    message:
      "Build equipped. Start a fresh agent session to use your updated skills.",
    success: true,
  });
}

export async function undoAppliedBuild(): Promise<void> {
  const revisionId = editor.view?.revisionId;

  if (
    !revisionId ||
    !window.confirm(
      "Restore the files from before the last apply? Later edits will be preserved if they conflict.",
    )
  ) {
    return;
  }

  await request({
    path: "/api/undo",
    schema: applyResultSchema,
    body: { revisionId },
  });

  notice({ message: "Restored the previous build.", success: true });
}
