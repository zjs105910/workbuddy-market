import {
  effectiveProfileStatus,
  type ProfileRule,
  type ProfileSnapshot,
} from "@shadowclone/profile";

export function normalizeExplicitCandidates(profile: ProfileSnapshot): {
  readonly profile: ProfileSnapshot;
  readonly promoted: readonly ProfileRule[];
} {
  const promoted: ProfileRule[] = [];
  const rules = profile.rules.map((snapshot) => {
    const status = effectiveProfileStatus(snapshot.rule);

    if (status === snapshot.rule.status) {
      return snapshot;
    }

    const rule: ProfileRule = { ...snapshot.rule, status };

    promoted.push(rule);

    return { ...snapshot, rule };
  });

  return { profile: { ...profile, rules }, promoted };
}
