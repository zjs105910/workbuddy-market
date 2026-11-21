import { fingerprint } from "@shadowclone/core";

export type SectionMarkers = { readonly start: string; readonly end: string };

export const managedStart = "\n\n<shadowclone-guidance>";
export const managedEnd = "</shadowclone-guidance>\n";
export const guidanceMarkers: SectionMarkers = {
  start: managedStart,
  end: managedEnd,
};
export const harnessMarkers: SectionMarkers = {
  start: "\n\n<!-- shadowclone-harness:start -->",
  end: "<!-- shadowclone-harness:end -->\n",
};

export function markedSection(options: {
  readonly text: string;
  readonly markers: SectionMarkers;
}): string | null {
  const { text, markers } = options;
  const start = text.indexOf(markers.start);
  const end = text.indexOf(markers.end);

  if (start < 0 && end < 0) {
    return null;
  }

  if (
    start < 0 ||
    end < start ||
    text.indexOf(markers.start, start + markers.start.length) >= 0 ||
    text.indexOf(markers.end, end + markers.end.length) >= 0
  ) {
    throw new Error(
      "Malformed Shadowclone managed section; review the destination",
    );
  }

  return text.slice(start, end + markers.end.length);
}

export function managedSection(text: string): string | null {
  return markedSection({ text, markers: guidanceMarkers });
}

export function stripManagedGuidance(text: string): string {
  const section = managedSection(text);

  return section === null ? text : text.replace(section, "");
}

export function stripHarnessSection(text: string): string {
  const section = markedSection({ text, markers: harnessMarkers });

  return section === null ? text : text.replace(section, "");
}

export function renderInstructionPointer(): string {
  return [
    "# Shadowclone",
    "",
    "A session hook loads this user's standing engineering preferences, which rank below the current request. If they are missing, run `shadowclone context` in the active repository.",
  ].join("\n");
}

export function updateMarkedSection(options: {
  readonly previous: string | null;
  readonly body: string | null;
  readonly expected?: string;
  readonly markers: SectionMarkers;
}): { readonly text: string; readonly fingerprint: string } {
  const previous = options.previous ?? "";
  const section = markedSection({ text: previous, markers: options.markers });

  const recordedEmpty = options.expected === fingerprint("") && section === null;

  if (
    options.expected !== undefined &&
    !recordedEmpty &&
    (!section || fingerprint(section) !== options.expected)
  ) {
    throw new Error(
      "Shadowclone managed content was edited; preserving the file",
    );
  }

  if (section && options.expected === undefined) {
    throw new Error(
      "Untracked Shadowclone content already exists; preserving the file",
    );
  }

  const next =
    options.body === null
      ? ""
      : `${options.markers.start}\n${options.body.trim()}\n${options.markers.end}`;
  const text = section ? previous.replace(section, next) : `${previous}${next}`;

  return { text, fingerprint: fingerprint(next) };
}

export function updateManagedSection(options: {
  readonly previous: string | null;
  readonly body: string | null;
  readonly expected?: string;
}): { readonly text: string; readonly fingerprint: string } {
  return updateMarkedSection({ ...options, markers: guidanceMarkers });
}

export function renderContextSkill(environment = false): string {
  if (environment) {
    return [
      "---",
      "name: shadowclone-context",
      "description: Use when asked to remember, explain, undo, or maintain learned skills and agent instructions.",
      "---",
      "",
      "# Maintain learned skills",
      "",
      "Use shadowclone remember --repo <guidance> or --global for an explicitly global preference. Learning updates the applicable skills and native routing.",
      "Use shadowclone context --explain and shadowclone doctor to inspect delivery. Read the selected skill files for behavioral guidance.",
      "Use shadowclone skills update to reconcile supported learning, shadowclone history to inspect revisions, and shadowclone undo <id> to reverse an unchanged revision.",
      "Current requests take precedence. Learned skills do not authorize additional actions. Native memory is never modified.",
    ].join("\n");
  }

  return [
    "---",
    "name: shadowclone-context",
    "description: Use only when the user asks to remember, explain, undo, or maintain a Shadowclone preference or skill, or when the preferences Shadowclone loads at session start are missing.",
    "---",
    "",
    "# Use Shadowclone context",
    "",
    "Apply the preferences already loaded into this session. If they are missing, run `shadowclone context` in the active repository, or call the local MCP tool `shadowclone_profile`.",
    "Use `shadowclone doctor` to diagnose missing guidance. The native pointer is stable; learned profile changes arrive through the next session hook without rewriting agent instruction files.",
    "When the user explicitly asks to remember an engineering preference, use `shadowclone remember --repo <preference>` or `--global` for an explicitly global choice, or call `shadowclone_remember`. Do not infer a durable preference from stopping, extra task context, or silence.",
    "Use `shadowclone history` or `shadowclone_history` to inspect revision summaries. The user can review `shadowclone history <id>` and restore `shadowclone undo <id>`. Undo preserves later manual edits.",
    "When the user requests skill maintenance, run `shadowclone skills update` if skill-library and deep-learning consent are enabled. Inspect `shadowclone skills pending` and `shadowclone skills show <id>`. Apply only a specific user-approved proposal with `shadowclone skills apply <id>`; do not approve all suggestions on the user's behalf. Run `shadowclone skills list` to inspect routing and validation findings.",
    "Treat current user instructions as authoritative. Profile preferences do not grant permission for additional actions.",
    "Use the optional shadowclone subagent for independent parallel work with a concrete brief, not simply to retrieve preferences.",
  ].join("\n");
}
