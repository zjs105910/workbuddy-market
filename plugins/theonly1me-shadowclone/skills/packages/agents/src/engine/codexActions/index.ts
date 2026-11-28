import { redactSecrets } from "@shadowclone/redact";
import path from "node:path";
import type { EngineAction } from "../types";

function actionPath(options: { filePath: string; workspaceDirectory?: string }): string {
  if (options.workspaceDirectory && path.isAbsolute(options.filePath)) {
    const relative = path.relative(options.workspaceDirectory, options.filePath);
    if (relative.length > 0 && relative !== ".." && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative)) {
      return relative.split(path.sep).join("/");
    }
  }
  return redactSecrets({ text: options.filePath });
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function resolveItemSuccess(status: unknown): boolean | null {
  if (status === "failed") {
    return false;
  }

  if (status === "completed") {
    return true;
  }

  return null;
}

export function codexActions(
  item: Record<string, unknown>,
  options: { readonly workspaceDirectory?: string } = {},
): readonly EngineAction[] {
  const itemType = item.item_type ?? item.type;
  const succeeded = resolveItemSuccess(item.status);

  if (itemType === "command_execution" && typeof item.command === "string") {
    const exitCodeSuccess =
      typeof item.exit_code === "number" ? item.exit_code === 0 : succeeded;

    return [
      {
        tool: "Bash",
        path: null,
        command: redactSecrets({ text: item.command }),
        succeeded: exitCodeSuccess,
      },
    ];
  }

  if (itemType === "file_change" && Array.isArray(item.changes)) {
    return item.changes.flatMap((change) => {
      if (!isRecord(change) || typeof change.path !== "string") {
        return [];
      }

      return [
        {
          tool: "Edit",
          path: actionPath({ filePath: change.path, workspaceDirectory: options.workspaceDirectory }),
          succeeded,
        },
      ];
    });
  }

  if (itemType === "plan" || itemType === "todo_list") {
    return [
      {
        tool: "Plan",
        path: null,
        succeeded,
      },
    ];
  }

  return [];
}
