import { projectPaths } from "@shadowclone/core";
import {
  pendingLearningRecords,
  readRedactedEnvironment,
  reviewLearning,
  setAutomaticMaintenance,
} from "@shadowclone/environment";
import { listSkillProposals } from "@shadowclone/skills";

export async function handleEnvironmentSkills(
  arguments_: readonly string[],
): Promise<boolean> {
  const [action, key, ...rest] = arguments_;
  const state = await readRedactedEnvironment(projectPaths);

  if (state === null) {
    return false;
  }

  if (
    action === "automatic" &&
    (key === "on" || key === "off") &&
    rest.length === 0
  ) {
    await setAutomaticMaintenance({
      paths: projectPaths,
      enabled: key === "on",
    });
    console.log(
      `Automatic supported skill maintenance ${key}. Source consent is configured separately.`,
    );
  } else if (action === "pending" && !key) {
    const pending = [
      ...pendingLearningRecords({ paths: projectPaths, state }),
      ...(await listSkillProposals(projectPaths)).filter(({ status }) => status === "pending"),
    ];

    console.log(JSON.stringify(pending, null, 2));
  } else if ((action === "retry" || action === "exclude") && key) {
    await reviewLearning({
      paths: projectPaths,
      key,
      action,
      reason: rest.join(" "),
    });
    console.log(
      action === "retry"
        ? "Learning queued for the next skills update."
        : "Learning excluded with the recorded reason.",
    );
  } else {
    return false;
  }

  return true;
}
