#!/bin/bash
# planning-with-files: Stop hook for Codex

# issue #195: per-invocation opt-out for one-shot/CI sessions.
[ "${PLANNING_DISABLED:-}" = "1" ] && exit 0

HOOK_DIR="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
PLAN_DIR="$(sh "${HOOK_DIR}/resolve-plan-dir.sh" 2>/dev/null)"
if [ -z "$PLAN_DIR" ] && [ "$(sh "${HOOK_DIR}/resolve-plan-dir.sh" --check-ambiguity 2>/dev/null)" = "PWF_PLAN_AMBIGUOUS_V1" ]; then
    exit 0
fi
# An explicit PLAN_ID is a binding, not a hint (issue #237). When the shared
# resolver rejected one it emits nothing, and the legacy-root fallback below
# would decide whether this run may stop from a plan the operator never named.
# Allow the stop rather than gating on the wrong plan.
[ -z "$PLAN_DIR" ] && [ -n "${PLAN_ID:-}" ] && exit 0
PLAN_FILE="${PLAN_DIR:+${PLAN_DIR}/}task_plan.md"

if [ ! -f "$PLAN_FILE" ]; then
    exit 0
fi

# Codex supports a native Stop continuation decision. Delegate the decision to
# the existing v3 gate oracle so Codex and skill-frontmatter installs share the
# same opt-in mode, in_progress, recursion, cap, and stall guards. Outside a
# gated block the oracle is advisory. Incomplete plans retain their notice;
# completed plans need no followup message.
CHECK_COMPLETE="${HOOK_DIR}/../skills/planning-with-files/scripts/check-complete.sh"
if [ "${1:-}" != "--stop-hook-active" ] && [ -f "${CHECK_COMPLETE}" ]; then
    GATE_OUTPUT="$(sh "${CHECK_COMPLETE}" --gate "${PLAN_FILE}")"
    case "${GATE_OUTPUT}" in
        '{"decision":"block"'*)
            printf '%s\n' "${GATE_OUTPUT}"
            exit 0
            ;;
    esac
fi

TOTAL=$(grep -c "### Phase" "$PLAN_FILE" || true)
COMPLETE=$(grep -cF "**Status:** complete" "$PLAN_FILE" || true)
IN_PROGRESS=$(grep -cF "**Status:** in_progress" "$PLAN_FILE" || true)
PENDING=$(grep -cF "**Status:** pending" "$PLAN_FILE" || true)

if [ "$COMPLETE" -eq 0 ] && [ "$IN_PROGRESS" -eq 0 ] && [ "$PENDING" -eq 0 ]; then
    COMPLETE=$(grep -c "\[complete\]" "$PLAN_FILE" || true)
    IN_PROGRESS=$(grep -c "\[in_progress\]" "$PLAN_FILE" || true)
    PENDING=$(grep -c "\[pending\]" "$PLAN_FILE" || true)
fi

: "${TOTAL:=0}"
: "${COMPLETE:=0}"
: "${IN_PROGRESS:=0}"
: "${PENDING:=0}"

# issue #191: a task_plan.md with no "### Phase" headings is not phase-structured.
# Without this guard the hook emits a false "0/0 phases complete" followup_message.
if [ "$TOTAL" -eq 0 ]; then
    exit 0
fi

if [ "$COMPLETE" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
    exit 0
fi

echo "{\"followup_message\": \"[planning-with-files] Task in progress ($COMPLETE/$TOTAL phases complete). If ending this turn, make sure progress.md is up to date.\"}"
exit 0
