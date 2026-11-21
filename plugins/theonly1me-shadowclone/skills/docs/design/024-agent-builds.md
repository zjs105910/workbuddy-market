# Agent builds

## Problem

The terminal wizard exposed choices without a persistent visual editor. A selected preference could stay unpublished until learning ran. Two related defects affected publication. Concurrent calls could each receive the same unspent dollar allowance. A repository refresh could erase checks when profile prose became skill routing.

## Decision

Provide one editable build per scope through shared preview and apply operations. The browser wizard opens with `shadowclone wizard`. `--cli` selects the terminal interface. Both publish the same portable skills, native instructions, and reversible revisions.

Users can equip bundled or consented existing skills, edit user-owned instructions, and create custom skills. Selecting preferences publishes them immediately. Global builds provide personal defaults. Repository builds refine them without weakening shared requirements. Provider-owned packages stay read-only, with reviewed personal changes in local companions.

Private repository output stays untracked. Shared output contains explicitly reviewed portable content and relative paths. Preview fingerprints stop the editor from overwriting intervening edits. Native providers may still discover a global skill that repository routing omits, so the editor must show the difference between routing and activation.

Organize every skill into a deterministic constellation. Derive it from the skill's declared category, axis, name, and short description. The library produces four to twelve top-level hubs. Nested hubs start once a group exceeds ten skills. Each skill has one primary parent and at most two related-hub links. Exact duplicate content appears once. Distinct skills with the same name stay separate. This presentation does not change build inputs, saved choices, or published guidance.

Render the constellation on a bounded canvas with measured pixel coordinates, so stars keep their shape. Support pan, zoom, fit, reset, search-and-center, hub focus, keyboard activation, and touch input. Provide an equivalent list view on narrow screens and as an explicit accessibility choice. Individual stars drift, twinkle, and fade independently. They do not restart when a skill changes. Ambient lighting stays consistent. Each equipped skill keeps its own illumination. The live build summary stays beside the constellation.

Use the focused D3 hierarchy, selection, and zoom modules for tree layout and input transforms. These packages replace custom geometry and gesture handling. Grouping, identity, and saved build state stay in the typed modules of Shadowclone.

Derive the build identity and traits from the equipped hubs. The local fallback uses the strongest hub and never needs a model. An optional reviewed model action can refine the hub labels and the identity from redacted hub summaries and selected titles. It never receives skill bodies, file paths, repository names, or owner metadata. Its output is interface copy, never guidance that Shadowclone injects.

The creation dialog offers Use AI alongside manual editing. It sends only the current form fields, after the user reviews the redacted payload, destination, and limits. Generated names, triggers, and instructions stay an editable draft until the user adds the skill and reviews publication. Failures and cancellation keep the original fields. Both model actions share bounded no-tools execution and reject duplicate submissions.

Every dialog supports an explicit close control, Escape, and clicking its backdrop. Dismissing a generation request aborts it and keeps the current form. Provider failures show a bounded, redacted diagnostic. The user can then tell authentication errors, usage limits, and provider errors apart without guessing.

Browser model output uses JSON Schema Draft 7, matching the supported Claude CLI contract. A local check rejects the default Draft 2020-12 declaration of Zod before a model request.

## Budget and check preservation

Fix shared budget accounting before editor model calls depend on it. Serialize calls that share a dollar cap. Calculate the allowance at dispatch. Stop further calls after unknown spend. Keep explicit repository checks during refresh. Changing them needs review.

## Data handling

Bind the browser server to loopback. Authenticate its API with an ephemeral token. Validate origins. Opening the editor enables neither capture nor model access. Reading existing skills needs consent. Editing authorizes only reviewed writes. Accept validated domain operations, never arbitrary file paths or shell commands.

Show the payload and destination before optional bounded model descriptions or skill drafts. Form drafting reads no repository files and adds no capture consent. Keep private evidence and identifying paths outside the public checkout and package. Native memory remains read-only.

## Verification

Cover shared-budget exhaustion and unknown costs, check preservation, immediate preference delivery, terminal and browser parity, scope, conflicts, undo, and unauthorized requests. Test the local browser and a relocated packed installation. Behavioral evaluations remain separate from synthetic packaging and interface checks.

The comment check must use parsed token boundaries. Then it treats interpolated local URLs as strings. Comments inside interpolation expressions stay violations.

Packaged browser routes serve only files from the generated asset manifest, which they find beside the installed bundle. Public asset URLs keep their relative layout. If someone starts the CLI from a work repository, the asset lookup must not depend on the working directory of that repository.

Test grouping, nesting, related links, stable output, duplicate handling, and identity derivation with synthetic libraries. Test libraries of one, twenty, one hundred, and five hundred items in a headless browser. Confirm these points:

- The page stays bounded.
- Stars keep equal horizontal and vertical scale.
- Controls are keyboard accessible.
- The list view exposes the same skills.
