#!/bin/bash
# planning-with-files: Post-tool-use hook for Codex

# issue #195: per-invocation opt-out for one-shot/CI sessions.
[ "${PLANNING_DISABLED:-}" = "1" ] && exit 0

HOOK_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
PLAN_DIR="$(sh "${HOOK_DIR}/resolve-plan-dir.sh" 2>/dev/null)"
if [ -z "$PLAN_DIR" ] && [ "$(sh "${HOOK_DIR}/resolve-plan-dir.sh" --check-ambiguity 2>/dev/null)" = "PWF_PLAN_AMBIGUOUS_V1" ]; then
    exit 0
fi
# An explicit PLAN_ID is a binding, not a hint (issue #237). When the shared
# resolver rejected one it emits nothing, and the legacy-root fallback below
# would answer for a plan the operator never named. Stay silent instead; the
# once-per-turn user-prompt-submit hook carries the notice.
[ -z "$PLAN_DIR" ] && [ -n "${PLAN_ID:-}" ] && exit 0
PLAN_FILE="${PLAN_DIR:+${PLAN_DIR}/}task_plan.md"

[ -f "$PLAN_FILE" ] || exit 0

# --- Once-per-turn throttle (issue #239). ---
# The reminder is a constant string, so every repeat after the first in a turn
# carries no information: it names no tool, no file and no phase. The Codex
# matcher fired on every shell command, so a session running twenty of them got
# twenty identical lines. user-prompt-submit.sh fires once per turn and clears
# this marker; the first post-tool fire of the turn sets it.
#
# The marker lives in the user's private cache, never in the plan directory:
# that directory is shared project state. Cache root and key derivation match
# hooks/claude-hook.sh and the slots inject-plan.sh already uses, so the two
# routes throttle the same way. When no cache root can be created the throttle
# is skipped rather than the nudge suppressed, so a broken cache cannot
# silently remove the reminder.
if [ -n "${XDG_CACHE_HOME:-}" ]; then
    TURN_ROOT="${XDG_CACHE_HOME}/pwf-turn"
elif [ -n "${HOME:-}" ]; then
    TURN_ROOT="${HOME}/.cache/pwf-turn"
else
    TURN_ROOT="${TMPDIR:-/tmp}/pwf-turn"
fi
TURN_MARKER=""
if mkdir -p "$TURN_ROOT" 2>/dev/null; then
    case "$PLAN_FILE" in
        /*|[A-Za-z]:*|\\\\*) TURN_KEY_SRC="$PLAN_FILE" ;;
        *) TURN_KEY_SRC="${PWD}/${PLAN_FILE}" ;;
    esac
    TURN_KEY_SRC="${TURN_KEY_SRC}|${PWF_SESSION_ID:-}"
    TURN_KEY=$(printf '%s' "$TURN_KEY_SRC" \
        | { sha256sum 2>/dev/null || shasum -a 256 2>/dev/null; } \
        | awk '{print $1}' | cut -c1-16)
    [ -n "$TURN_KEY" ] && TURN_MARKER="${TURN_ROOT}/${TURN_KEY}"
fi
if [ -n "$TURN_MARKER" ]; then
    [ -e "$TURN_MARKER" ] && exit 0
    : > "$TURN_MARKER" 2>/dev/null || :
fi

echo "[planning-with-files] Update progress.md with what you just did. If a phase is now complete, update task_plan.md status."
exit 0
