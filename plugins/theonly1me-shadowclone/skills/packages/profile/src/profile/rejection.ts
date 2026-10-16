export type ProfileRejectionReason =
  | "skill-covered"
  | "repo-covered"
  | "stale"
  | "synthetic"
  | "one-off"
  | "duplicate"
  | "user-rejected";

export function isRejectionReason(
  value: unknown,
): value is ProfileRejectionReason {
  return (
    value === "skill-covered" ||
    value === "repo-covered" ||
    value === "stale" ||
    value === "synthetic" ||
    value === "one-off" ||
    value === "duplicate" ||
    value === "user-rejected"
  );
}
