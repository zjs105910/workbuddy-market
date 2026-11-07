export const existingManualSkill = `---
name: personal-engineering
description: Coding style when implementing and reviewing TypeScript modules.
---

# Engineering defaults

Use clear types, narrow unknown values, and avoid any, casts, and non-null assertions. Literal as const is fine.
Let names and small functions explain code. Do not add code comments unless the current request asks for them.
For new functions taking multiple inputs, accept one named options object. Preserve established single-input APIs.
`;

export const intendedGlobalSkill = `---
name: personal-workflow
description: Personal defaults for final answers and authorization of Git and remote actions.
---

# Work completion

Use no more than eighty words (80) in a final answer, including any code. An explicit current request for a longer explanation overrides this limit.
Leave work ready to review and propose one lowercase conventional commit subject. Wait for an explicit request before committing or changing branches; an explicit commit request already provides approval. Readiness language alone grants no push or PR authority.
`;

export const intendedAtlasSkill = `---
name: atlas-engineering
description: Atlas regression fixes, lookup APIs, and authorized pull requests. Applies only in Atlas.
---

# Atlas engineering

For bug fixes, edit a regression test and observe a failing run before the first production edit. Follow a one-task waiver without changing this default for later tasks.
An authorized PR has a concrete title without ticket numbers and a Changes heading containing one-sentence checklist items. Follow an explicitly requested alternative body format instead.
Atlas lookups return { ok: true, value } or { ok: false, error }. This supersedes the earlier throwing convention here. It does not change other repositories.
`;
