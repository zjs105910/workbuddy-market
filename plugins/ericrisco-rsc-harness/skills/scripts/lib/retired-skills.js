// Skills the catalog no longer ships, and the skill that took over their job.
//
// `eli5` and `show-me` folded into `orient`, which explains at the register `technical_level` asks
// for; `bro` folded into `unslop`, which rewrites text meant for other people. A harness built before
// that still names them — in `.rsc.json`, in per-target state, and inside the onboarding receipt,
// which is hash-checked against what the user accepted and therefore never rewritten. So every reader
// of a DECLARED skill list maps through here, instead of each one learning the history on its own.
//
// `targets/clone-bootstrap.mjs` is committed into user repos and cannot import this file; it carries
// an inline copy, and tests/retired-skills.test.js holds the two equal in behaviour.
export const RETIRED_SKILLS = Object.freeze({ eli5: 'orient', 'show-me': 'orient', bro: 'unslop' });

const retiredTo = (id) => (Object.hasOwn(RETIRED_SKILLS, id) ? RETIRED_SKILLS[id] : id);

/** Each retired id becomes its successor; order of first appearance kept, duplicates dropped. */
export function replaceRetired(ids = []) {
  return [...new Set((ids || []).map(retiredTo))];
}

export const isRetired = (id) => Object.hasOwn(RETIRED_SKILLS, id);
