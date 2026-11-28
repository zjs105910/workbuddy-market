import { runLearningService } from "@shadowclone/learning";
import { promptConfirmation } from "./confirm";

export type { DeepLearningResult } from "@shadowclone/learning";

export async function runDeepLearning(
  options: Parameters<typeof runLearningService>[0],
): ReturnType<typeof runLearningService> {
  return runLearningService({
    ...options,
    confirm: options.confirm ?? promptConfirmation,
  });
}
