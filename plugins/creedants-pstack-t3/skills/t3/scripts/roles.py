#!/usr/bin/env python3
"""Resolve pstack-t3 roles into T3 delegate_task targets.

Roles map a pstack role name to a list of seats. A seat is "inherit" or a
target {"providerInstanceId", "model", "options"} drawn from the catalog that
T3's orchestrator_capabilities tool returns.
"""

import argparse
import fnmatch
import json
import os
import posixpath
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

SINGLE_ROLES = [
    "feature, refactoring",
    "bug-fix",
    "perf-issue",
    "hillclimb",
    "judgment and prose",
    "hardest tasks",
    "how explorer",
    "how explainer",
    "why investigators",
    "why synthesizer",
    "reflect tooling",
    "reflect judgment, divergent, synthesizer",
    "swarm workers",
    "skill tests",
]
PANEL_ROLES = [
    "arena runners",
    "arena cross-judge pool",
    "architect runners",
    "interrogate reviewers",
    "verifiers",
    "review backups",
]
ROLES = SINGLE_ROLES + PANEL_ROLES
BUDGETS = {"default": None, "small": "medium", "medium": "high", "large": "xhigh", "unlimited": "max"}
MODES = ("full", "light")
ATTEMPTS = ("first", "fix", "bounce")
EFFORT_IDS = ("effort", "reasoningEffort", "reasoning_effort", "reasoning")
LADDER = {"none": 0, "minimal": 1, "low": 2, "medium": 3, "high": 4, "xhigh": 5, "extra-high": 5, "extra_high": 5, "max": 6, "ultra": 7}
SPECIAL = {"ultracode", "ultrathink"}
INHERIT = "inherit"
CANNOT_LAUNCH_SEATS = frozenset({"cursor"})   # its harness sends target.options as a JSON string, which T3 refuses
DRIVER_RUNTIME_MODES = {"muse": frozenset({"approval-required", "full-access"})}
FAST_GROK_OPTIONS = frozenset({"fastMode"})  # the user never runs a Grok model in its fast variant
HAIKU_BRIEF = (
    "Keep working until everything the user asked for is done, and only stop to ask when you can't go on without the user or before a risky step. When the work the user asked for is done and checked, stop and report. Don't add new features, docs, or refactors that weren't asked for. If you think one would help, mention it at the end instead of doing it.",
    "When you change code that can be run, built, or type-checked, run a real check that exercises the change before reporting it done: the project's tests, type-checker, or build, or the changed command itself. A syntax-only check, or a check command that failed to start, does not count; if all that is missing is the project's declared dependencies, install them with its own package manager and lockfile (e.g. npm install, pip install -r requirements.txt), never via sudo or the system package manager, unless told not to. Only if no real check can run here, say which one you did not run and why instead of reporting the change as done.",
)
CATALOG_REQUIRED = "catalog-required"
DEFAULT_PANEL = "default-panel"


class RolesError(Exception):
    pass


class ModeSettingsError(RolesError):
    """A mode setting or mode input this version rejects."""


@dataclass(frozen=True)
class ModeDecision:
    """One mode decision and where it came from.

    label is the brief grammar's Mode source value. where is what show prints
    as modeSource. A file level uses the file path. Every other level uses the label.
    """

    mode: str
    label: str
    where: str


DEFAULT_MODE = ModeDecision("full", "default", "default")


def effective_mode(config, brief=None, session=None, coordinator=None):
    """Brief, then session, then coordinator, then the merged file level, then full."""
    for value, label in ((brief, "brief"), (session, "session"), (coordinator, "restaurant.json")):
        if value is not None:
            return ModeDecision(value, label, label)
    return config.get("mode", DEFAULT_MODE)


def seat_budget(budget, mode):
    """Light caps only a default budget. An explicit budget wins both ways."""
    return "small" if mode == "light" and budget == "default" else budget


NO_CATALOG_INFO = (
    "info: light mode caps reasoning at medium, but show had no catalog, "
    "so no seat was capped. Rerun with --catalog and --parent."
)
NO_PARENT_INFO = (
    "info: light mode caps reasoning at medium, but show had no --parent, "
    "so an inherit seat may keep the parent's reasoning. Rerun with --parent."
)


def light_cap_gap(decision, budget, has_catalog, has_parent):
    """The info line show prints when the light cap may not have reached every seat."""
    if seat_budget(budget, decision.mode) == budget:
        return None
    if not has_catalog:
        return NO_CATALOG_INFO
    if not has_parent:
        return NO_PARENT_INFO
    return None


@dataclass(frozen=True)
class Parent:
    provider: str
    model: str


@dataclass(frozen=True)
class PreferredSeat:
    """A built-in seat. effort is the level it promises. unlimited is the level the unlimited budget asks for.

    The shortfall note compares the chosen level with effort, so asking for more never adds a note.
    """

    model_id: str
    effort: str = "xhigh"
    unlimited: str = "max"

    def level(self, budget):
        return self.unlimited if budget == "unlimited" else self.effort


class AdaptiveDefault(Enum):
    VERIFIERS = "verifiers"
    UNSET = "unset"


OPUS = PreferredSeat("claude-opus-5-5", "xhigh", "max")
GROK = PreferredSeat("grok-4.7", "xhigh", "max")
HAIKU_TESTS = PreferredSeat("claude-haiku-5-5", "high", "high")
HAIKU_READING = PreferredSeat("claude-haiku-5-5", "medium", "medium")

ROLE_DEFAULTS = {
    "feature, refactoring": (GROK,),
    "bug-fix": (GROK,),
    "perf-issue": (GROK,),
    "hillclimb": (GROK,),
    "judgment and prose": (OPUS,),
    "hardest tasks": (OPUS,),
    "how explorer": (HAIKU_READING,),
    "how explainer": (OPUS,),
    "why investigators": (HAIKU_READING,),
    "why synthesizer": (OPUS,),
    "reflect tooling": (GROK,),
    "reflect judgment, divergent, synthesizer": (OPUS,),
    "swarm workers": (GROK,),
    "arena runners": (OPUS, GROK),
    "arena cross-judge pool": (OPUS, GROK),
    "architect runners": (OPUS, GROK),
    "interrogate reviewers": (OPUS, GROK),
    "skill tests": (HAIKU_TESTS,),
    "verifiers": AdaptiveDefault.VERIFIERS,
    "review backups": AdaptiveDefault.UNSET,
}


@dataclass(frozen=True)
class DefaultSelection:
    seats: object
    notes: tuple = ()


# A usage limit moves along this ladder. Nothing here searches for the first runnable model.
LIGHT_ROLES = frozenset(
    name for name, policy in ROLE_DEFAULTS.items()
    if isinstance(policy, tuple) and policy[0] in (HAIKU_TESTS, HAIKU_READING)
)
REVIEW_ROLES = frozenset({"verifiers", "interrogate reviewers", "arena cross-judge pool"})
NEVER_BACKUP_PROVIDERS = frozenset({"codex", "cursor"})
CLAUDE_BACKUP_PROVIDER = "claudeAgent"
WORKER_BACKUP = "claude-opus-5-5"
LIGHT_BACKUP = "claude-sonnet-5-5"
REVIEW_LADDER = ("grok-4.7", "claude-opus-5-5")
PANEL_GATE_ROLE = "verifiers"
PANEL_BACKUP_ROLE = "review backups"
# Resume returns none of these to a seat in an author family.
AUTHOR_CHECKED_ROLES = REVIEW_ROLES | {PANEL_BACKUP_ROLE}
PANEL_MINIMUM_PASSES = 2
PANEL_MAXIMUM_REPRODUCED_BLOCKERS = 0
PANEL_RULE = {
    "waitForAllTerminal": True,
    "minimumPasses": PANEL_MINIMUM_PASSES,
    "maximumReproducedBlockers": PANEL_MAXIMUM_REPRODUCED_BLOCKERS,
}
UNSET_NOTE = (
    "review backups has no built-in seats. Set it to let roles.py backup run a review panel "
    "when every paid reviewer backup is out. Unset, a verifier parks."
)
PANEL_CATALOG_NOTE = (
    "review backups drops seats by the catalog: "
    "call orchestrator_capabilities and rerun roles.py show --catalog"
)
BACKUP_PROVIDERS = {
    WORKER_BACKUP: CLAUDE_BACKUP_PROVIDER,
    LIGHT_BACKUP: CLAUDE_BACKUP_PROVIDER,
    "grok-4.7": "grok",
}
USAGE_LIMIT_PATTERNS = tuple(re.compile(pattern, re.I) for pattern in (
    r"you['’]?ve hit your (?:usage )?limit\b",
    r"usage limit reached",
    r"reached your usage limit",
    r"usage limit exceeded",
    r"out of usage",
    r"quota exceeded",
    r"exceeded your quota",
    r"insufficient_quota",
    r"usage balance exhausted",
))


@dataclass(frozen=True)
class Backup:
    """One usage-limit decision. relaunch carries a seat. panel carries seats and drop notes."""

    decision: str
    report: str
    seat: dict | None = None
    seats: tuple | None = None
    notes: tuple = ()


def user_config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "pstack-t3" / "roles.json"


def snapshot_path():
    return user_config_path().with_name("catalog.json")


def project_config_path(cwd):
    current = Path(cwd).resolve()
    for directory in [current, *current.parents]:
        candidate = directory / ".pstack" / "t3-roles.json"
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists():
            return directory / ".pstack" / "t3-roles.json"
    return current / ".pstack" / "t3-roles.json"


def parse_json(text, origin):
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise RolesError(f"{origin}: invalid JSON: {error}") from error


def load_json(path):
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return None
    return parse_json(text, path)


def load_catalog(path):
    data = parse_json(sys.stdin.read(), "-") if str(path) == "-" else load_json(path)
    if data is None:
        raise RolesError(f"{path}: catalog not found")
    if "providers" not in data:
        raise RolesError(f"{path}: not an orchestrator_capabilities result (no providers)")
    return data


def parse_seat(text):
    """Parse `inherit` or `provider/model[?option=value&option=value]`."""
    text = text.strip()
    if text == INHERIT:
        return INHERIT
    head, _, query = text.partition("?")
    provider, slash, model = head.partition("/")
    if not slash or not provider or not model:
        raise RolesError(f"seat {text!r}: expected 'inherit' or 'provider/model[?option=value]'")
    options = {}
    for pair in filter(None, query.split("&")):
        key, equals, value = pair.partition("=")
        if not equals:
            raise RolesError(f"seat {text!r}: option {pair!r} needs a value")
        options[key] = {"true": True, "false": False}.get(value, value)
    seat = {"providerInstanceId": provider, "model": model}
    if options:
        seat["options"] = options
    return seat


def bare_id(model_id):
    return model_id.rsplit("/", 1)[-1].lower()


def normalized_bare(model_id):
    """Canonical id both Haiku checks compare.

    Removes a provider path prefix such as amazon-bedrock/, a Vertex @YYYYMMDD
    suffix, and one leading Bedrock prefix (anthropic., or us., eu., apac., or
    global. before anthropic.). Then folds dots and underscores to hyphens and
    removes a trailing -YYYYMMDD suffix.
    """
    text = bare_id(model_id)
    text = re.sub(r"@\d{8}$", "", text)
    text = re.sub(r"^(?:(?:us|eu|apac|global)\.)?anthropic\.", "", text)
    text = text.replace(".", "-").replace("_", "-")
    return re.sub(r"-\d{8}$", "", text)


def family(model_id):
    """Leading word of normalized_bare(model_id).

    opencode/muse-2-free -> muse, us.anthropic.claude-sonnet-5-5-v1:0 -> claude.
    """
    text = normalized_bare(model_id)
    return re.split(r"[-\d]", text, maxsplit=1)[0] or text


def haiku_45(model_id):
    if not isinstance(model_id, str) or not model_id:
        return False
    return re.search(r"(?:^|-)claude-haiku-4-5(?:-|$)", normalized_bare(model_id)) is not None


def model_tokens(model_id):
    return re.split(r"[-_.]", model_id.lower())


def fast_grok(model_id):
    """A Grok id whose name marks its fast variant: grok-4.7-build-fast, x-ai/grok-code-fast-1."""
    if not isinstance(model_id, str) or not model_id:
        return False
    return family(model_id) == "grok" and "fast" in model_tokens(bare_id(model_id))


EXCLUDED_KINDS = (
    ("a fast Grok model", fast_grok),
    ("Claude Haiku 4.5", haiku_45),
)


def excluded_rule(labels):
    return f"pstack never runs {' or '.join(labels)} as a seat or a worker"


EXCLUDED_RULE = excluded_rule(label for label, _ in EXCLUDED_KINDS)


def excluded_id(model_id):
    return any(matches(model_id) for _, matches in EXCLUDED_KINDS)


def pickable(model_id):
    """An automatic picker may choose this model."""
    return not excluded_id(model_id)


def fast_options(model):
    """Fast boolean options this Grok model declares. Empty for every other family."""
    if family(model["id"]) != "grok":
        return []
    return [item["id"] for item in options_of(model) if item.get("id") in FAST_GROK_OPTIONS and item.get("type") == "boolean"]


def without_fast(seat, model):
    """Pin each fast option this Grok model declares off."""
    keys = fast_options(model)
    if not keys:
        return seat
    return {**seat, "options": {**(seat.get("options") or {}), **{key: False for key in keys}}}


def excluded_reason(seat):
    """Why this seat is excluded, or None. Needs no catalog."""
    if not isinstance(seat, dict):
        return None
    model_id = seat["model"]
    if fast_grok(model_id):
        return f"{bare_id(model_id)} is a fast Grok variant"
    if haiku_45(model_id):
        return f"{bare_id(model_id)} is Claude Haiku 4.5"
    on = sorted(key for key, value in (seat.get("options") or {}).items() if key in FAST_GROK_OPTIONS and value is True)
    if on and family(model_id) == "grok":
        return f"{on[0]}=true runs {bare_id(model_id)} fast"
    return None


def excluded_refusal(name, seat, *, inherit=False):
    reason = excluded_reason(seat)
    if reason is None:
        return None
    verb = "inherit" if inherit else "use"
    return f"role {name!r} cannot {verb} {seat['providerInstanceId']}/{seat['model']}: {reason}, and {EXCLUDED_RULE}"


def parse_parent(text):
    """Provider is the text before the first slash. The model id may contain slashes."""
    message = (
        f"--parent {text!r}: expected '<inheritedProviderInstanceId>/<inheritedModel>' "
        "from orchestrator_capabilities"
    )
    if not isinstance(text, str) or "/" not in text or any(char.isspace() for char in text) or "?" in text:
        raise RolesError(message)
    provider, _, model = text.partition("/")
    if not provider or not model:
        raise RolesError(message)
    return Parent(provider, model)


def inherit_parent(catalog):
    """Parent stored on a catalog file, or None when those keys are missing or malformed."""
    if not isinstance(catalog, dict):
        return None
    provider = catalog.get("inheritedProviderInstanceId")
    model = catalog.get("inheritedModel")
    if not isinstance(provider, str) or not isinstance(model, str) or not provider or not model:
        return None
    try:
        return parse_parent(f"{provider}/{model}")
    except RolesError:
        return None


def stamp_parent(catalog, parent):
    return {
        **catalog,
        "inheritedProviderInstanceId": None if parent is None else parent.provider,
        "inheritedModel": None if parent is None else parent.model,
    }


def is_snapshot_path(path):
    if path is None or str(path) == "-":
        return False
    try:
        return Path(path).resolve() == snapshot_path().resolve()
    except OSError:
        return False


def given_parent(args):
    text = getattr(args, "parent", None)
    if text is None:
        return None
    return parse_parent(text)


def given_runtime_mode(args):
    text = getattr(args, "runtime_mode", None)
    if text is None:
        return None
    if not text or any(char.isspace() for char in text):
        raise RolesError(f"--runtime-mode {text!r}: expected runtimeMode from orchestrator_capabilities")
    return text


def parent_for(args, catalog, catalog_path):
    """--parent wins. A snapshot never supplies a parent. An explicit catalog file does."""
    given = given_parent(args)
    if given is not None:
        return given
    if catalog is None or is_snapshot_path(catalog_path):
        return None
    return inherit_parent(catalog)


def _pool_providers(catalog, providers=None):
    """Runnable providers a picker may use, in catalog order. providers limits them to a launch pool."""
    return [
        provider for provider in catalog.get("providers") or []
        if (providers is None or provider["providerInstanceId"] in providers) and runnable(provider)
    ]


def no_seat_message(name, catalog, providers=None):
    pool = _pool_providers(catalog, providers)
    if providers is not None and not pool:
        return (
            f"role {name!r} has no seat: none of the providers it may use "
            f"({', '.join(sorted(providers))}) can run child tasks"
        )
    excluded = [model.get("id") for provider in pool for model in models_of(provider) if not pickable(model.get("id"))]
    labels = [label for label, matches in EXCLUDED_KINDS if any(matches(model_id) for model_id in excluded)]
    if providers is None:
        where = "in the catalog"
    else:
        where = f"on {', '.join(sorted(provider['providerInstanceId'] for provider in pool))}"
    return (
        f"role {name!r} has no seat: every runnable model {where} is excluded "
        f"({', '.join(dict.fromkeys(bare_id(model_id) for model_id in excluded))}), and {excluded_rule(labels)}"
    )


def no_runnable_provider(catalog):
    return not any(runnable(provider) for provider in (catalog or {}).get("providers") or [])


def canonical(path, kind="lease"):
    """Repository-relative POSIX path with no aliases. An empty string is the whole repository."""
    value = posixpath.normpath(path.strip().replace("\\", "/")).lstrip("/")
    if value in (".", ""):
        return ""
    if value == ".." or value.startswith("../"):
        raise ModeSettingsError(f"{kind} path {path!r} leaves the repository")
    return value


def lease_paths(text):
    """Leases land.py would claim for this comma-separated list."""
    return sorted({canonical(part) for part in text.split(",")})


def check_shape(config, origin):
    if not isinstance(config, dict):
        raise RolesError(f"{origin}: expected an object")
    budget = config.get("budget", "default")
    if budget not in BUDGETS:
        raise RolesError(f"{origin}: budget {budget!r} is not one of {', '.join(BUDGETS)}")
    if "mode" in config and config["mode"] not in MODES:
        raise ModeSettingsError(f"{origin}: mode {config['mode']!r} is not one of {', '.join(MODES)}")
    if "escalate" in config:
        escalate = config["escalate"]
        if not isinstance(escalate, list) or not all(isinstance(item, str) and item for item in escalate):
            raise ModeSettingsError(f"{origin}: escalate must be a list of strings")
        for item in escalate:
            try:
                canonical(item, "escalate pattern")  # traversal check only; the stored pattern stays raw
            except ModeSettingsError:
                raise ModeSettingsError(f"{origin}: escalate pattern {item!r} leaves the repository") from None
    roles = config.get("roles", {})
    if not isinstance(roles, dict):
        raise RolesError(f"{origin}: roles must be an object")
    for name, seats in roles.items():
        if name not in ROLES:
            raise RolesError(f"{origin}: unknown role {name!r}")
        if not isinstance(seats, list) or not seats:
            raise RolesError(f"{origin}: role {name!r} needs a non-empty list of seats")
        if name in SINGLE_ROLES and len(seats) != 1:
            raise RolesError(f"{origin}: role {name!r} takes exactly one seat")
        for seat in seats:
            if seat == INHERIT and name == PANEL_BACKUP_ROLE:
                raise RolesError(f"{origin}: role {name!r} refuses inherit, because the parent can be the author")
            if seat == INHERIT:
                continue
            if not isinstance(seat, dict) or not seat.get("providerInstanceId") or not seat.get("model"):
                raise RolesError(f"{origin}: role {name!r} has a seat without providerInstanceId and model")
    return config


def merged_config(cwd, user_path=None, project_path=None):
    user_path = Path(user_path) if user_path else user_config_path()
    project_path = Path(project_path) if project_path else project_config_path(cwd)
    user = check_shape(load_json(user_path) or {}, user_path)
    project = check_shape(load_json(project_path) or {}, project_path)
    roles, sources = {}, {}
    for origin, config in ((user_path, user), (project_path, project)):
        for name, seats in config.get("roles", {}).items():
            roles[name] = seats
            sources[name] = str(origin)
    if "mode" in project:
        mode = ModeDecision(project["mode"], ".pstack/t3-roles.json", str(project_path))
    elif "mode" in user:
        mode = ModeDecision(user["mode"], "roles.json", str(user_path))
    else:
        mode = DEFAULT_MODE
    escalate = list(project["escalate"]) if "escalate" in project else None
    budget = project["budget"] if "budget" in project else user.get("budget", "default")
    return {
        "budget": budget,
        "mode": mode,
        "escalate": escalate,
        "roles": roles,
        "sources": sources,
    }


def providers_by_id(catalog):
    return {provider["providerInstanceId"]: provider for provider in catalog["providers"]}


def models_of(provider):
    return (provider or {}).get("models") or []


def options_of(model):
    return (model or {}).get("options") or []


def runnable(provider):
    return bool(provider and provider.get("canRunChildTask") and models_of(provider))


def for_runtime_mode(catalog, mode):
    """Catalog copy in which a runnable provider cannot run children when DRIVER_RUNTIME_MODES lists its driver without the mode."""
    if catalog is None or mode is None:
        return catalog
    providers = []
    for provider in catalog.get("providers") or []:
        driver = provider.get("driverKind")
        modes = DRIVER_RUNTIME_MODES.get(driver)
        if modes is not None and mode not in modes and runnable(provider):
            provider = {
                **provider,
                "canRunChildTask": False,
                "constraints": [f"the {driver} driver lacks runtime mode {mode}"],
            }
        providers.append(provider)
    return {**catalog, "providers": providers}


def find_model(provider, model_id):
    return next((model for model in models_of(provider) if model["id"] == model_id), None)


def rank(value):
    return LADDER.get(value)


DEFAULT_FAMILIES = frozenset(
    family(preference.model_id) for policy in ROLE_DEFAULTS.values() if isinstance(policy, tuple) for preference in policy
)


def effort_option(model):
    return next((option for option in options_of(model) if option["id"] in EFFORT_IDS and option.get("type") == "select"), None)


def check_option_values(seat, model):
    """Return problems for option values the catalog does not offer."""
    problems = []
    declared = {option["id"]: option for option in options_of(model)}
    for key, value in (seat.get("options") or {}).items():
        option = declared.get(key)
        if option is None:
            continue
        if option.get("type") == "boolean" and not isinstance(value, bool):
            problems.append(f"option {key}={value!r} must be true or false")
        elif option.get("type") == "select":
            choices = [choice["id"] for choice in option.get("options") or []]
            if value not in choices:
                problems.append(f"option {key}={value!r} is not one of {', '.join(choices)}")
    return problems


def apply_level(seat, model, target_level):
    option = effort_option(model) if model else None
    if target_level is None or option is None:
        return seat
    values = [choice["id"] for choice in option.get("options") or [] if choice["id"] not in SPECIAL and rank(choice["id"]) is not None]
    if not values:
        return seat
    allowed = [value for value in values if rank(value) <= rank(target_level)] or [min(values, key=rank)]
    current = (seat.get("options") or {}).get(option["id"])
    chosen = current if current in allowed else max(allowed, key=rank)
    return {**seat, "options": {**(seat.get("options") or {}), option["id"]: chosen}}


def apply_budget(seat, model, budget):
    cap = BUDGETS[budget]
    if cap is None:
        return seat
    return apply_level(seat, model, cap)


def _runnable_rows(catalog, providers=None):
    return [
        (provider, model)
        for provider in _pool_providers(catalog, providers)
        for model in models_of(provider)
        if pickable(model["id"])
    ]


def _provider_for_exact(matches, wanted_family):
    """Prefer a provider whose first model shares the family. Otherwise catalog order."""
    fallback = None
    for provider, model in matches:
        if fallback is None:
            fallback = (provider, model)
        if family(models_of(provider)[0]["id"]) == wanted_family:
            return provider, model
    return fallback


def _preferred_seat(preference, catalog, budget="default", role=None, providers=None):
    """Return a concrete runnable target and explanations of changed intent."""
    if no_runnable_provider(catalog):
        raise RolesError("no provider in the catalog can run child tasks")
    rows = _runnable_rows(catalog, providers)
    if not rows:
        raise RolesError(no_seat_message(role or "bug-fix", catalog, providers))
    wanted = preference.model_id
    wanted_family = family(wanted)
    exact = [(provider, model) for provider, model in rows if model["id"] == wanted]
    cause = None
    if exact:
        provider, model = _provider_for_exact(exact, wanted_family)
    else:
        same_family = [(provider, model) for provider, model in rows if family(model["id"]) == wanted_family]
        if same_family:
            provider, model = same_family[0]
            cause = "missing model"
        else:
            parent_id = catalog.get("inheritedProviderInstanceId")
            parent_model_id = catalog.get("inheritedModel")
            parent = providers_by_id(catalog).get(parent_id) if parent_id else None
            parent_model = find_model(parent, parent_model_id) if runnable(parent) and parent_model_id else None
            if parent_model is not None and pickable(parent_model_id):
                provider, model = parent, parent_model
            else:
                provider, model = rows[0]
            cause = "missing family"
    target_level = preference.level(budget)
    seat = apply_level({"providerInstanceId": provider["providerInstanceId"], "model": model["id"]}, model, target_level)
    notes = []
    if cause is not None:
        notes.append(f"wanted {wanted}, using {provider['providerInstanceId']}/{model['id']} ({cause})")
    option = effort_option(model)
    chosen = (seat.get("options") or {}).get(option["id"]) if option else None
    if chosen is not None and rank(chosen) is not None and rank(preference.effort) is not None and rank(chosen) < rank(preference.effort):
        notes.append(f"wanted {preference.effort}, using {chosen}")
    return seat, tuple(notes)


def _first_pickable(provider):
    return next((model for model in models_of(provider) if pickable(model["id"])), None)


def _verifier_seats(catalog, role="verifiers"):
    """Inherit the runnable parent, then add one seat per new family.

    An excluded parent contributes no inherit seat and leaves its family open.
    Its provider's first pickable model can join. Repeat a lone seat to three.
    """
    parent = catalog.get("inheritedProviderInstanceId")
    parent_model = catalog.get("inheritedModel")
    parent_provider = providers_by_id(catalog).get(parent) if parent else None
    parent_runs = runnable(parent_provider) if parent else False
    parent_excluded = bool(parent_model) and excluded_id(parent_model)
    blocked = parent_excluded
    seats, families, notes = [], set(), []
    if parent_runs and parent_model and not blocked:
        seats.append(INHERIT)
        families.add(family(parent_model))
    elif parent_runs and parent_excluded:
        parent_seat = {"providerInstanceId": parent, "model": parent_model}
        reason = excluded_reason(parent_seat) or bare_id(parent_model)
        notes.append(
            f"skipped inherit of {parent}/{parent_model}: "
            f"{reason}, and {EXCLUDED_RULE}"
        )
    for provider in catalog["providers"]:
        if not runnable(provider):
            continue
        if parent_runs and not blocked and provider["providerInstanceId"] == parent:
            continue
        model = _first_pickable(provider)
        if model is None:
            continue
        model_id = model["id"]
        if family(model_id) in families:
            continue
        families.add(family(model_id))
        seats.append({"providerInstanceId": provider["providerInstanceId"], "model": model_id})
    if len(seats) == 1:
        seats = seats * 3
    elif not seats:
        if no_runnable_provider(catalog):
            raise RolesError("no provider in the catalog can run child tasks")
        raise RolesError(no_seat_message(role, catalog))
    return seats, notes


def _lost_diversity(name, seats):
    groups = {}
    for number, seat in enumerate(seats, 1):
        if not isinstance(seat, dict):
            continue
        groups.setdefault((seat["providerInstanceId"], seat["model"]), []).append(str(number))
    for (provider, model), numbers in groups.items():
        if len(numbers) > 1:
            joined = " and ".join(numbers)
            return f"{name}: seats {joined} both use {provider}/{model}, so the panel lost a distinct model"
    return None


def default_seats(name, catalog, budget="default", providers=None):
    """Resolve exactly the policy seats for this role from the live catalog."""
    policy = ROLE_DEFAULTS[name]
    if policy is AdaptiveDefault.UNSET:
        return DefaultSelection(policy.value, (UNSET_NOTE,))
    if catalog is None:
        if policy is AdaptiveDefault.VERIFIERS:
            return DefaultSelection(DEFAULT_PANEL, (
                "expand from orchestrator_capabilities: this thread inherits, then one seat per runnable provider whose first model is a new model family",
            ))
        return DefaultSelection(CATALOG_REQUIRED, (
            "call orchestrator_capabilities and rerun roles.py show --catalog",
        ))
    if policy is AdaptiveDefault.VERIFIERS:
        seats, notes = _verifier_seats(catalog, name)
        return DefaultSelection(tuple(seats), tuple(notes))
    seats, notes = [], []
    for number, preference in enumerate(policy, 1):
        seat, seat_notes = _preferred_seat(preference, catalog, budget, name, providers)
        seats.append(seat)
        notes.extend(f"{name} seat {number}: {note}" for note in seat_notes)
    diversity = _lost_diversity(name, seats)
    if diversity:
        notes.append(diversity)
    return DefaultSelection(tuple(seats), tuple(notes))


def _resolve_inherit(catalog, budget, name):
    """Settle an inherit seat and return resolve_seat's (seat, notes) shape.

    An excluded parent becomes its provider's first pickable model or is refused.
    A Grok parent that declares boolean fastMode becomes an explicit seat with
    fastMode false or is refused when its provider cannot run that seat.
    That note reads inherit made explicit as <provider>/<model> so fastMode stays false.
    """
    parent = inherit_parent(catalog)
    if parent is None:
        return INHERIT, []
    provider = providers_by_id(catalog).get(parent.provider)
    parent_seat = {"providerInstanceId": parent.provider, "model": parent.model}
    if excluded_id(parent.model):
        model = _first_pickable(provider) if runnable(provider) else None
        if model is None:
            raise RolesError(f"{excluded_refusal(name, parent_seat, inherit=True)}; {parent.provider} has no other model pstack may pick")
        seat = finish_seat({"providerInstanceId": parent.provider, "model": model["id"]}, model, budget)
        return seat, [f"inherit replaced by {parent.provider}/{model['id']}: {excluded_reason(parent_seat)}, and {EXCLUDED_RULE}"]
    model = find_model(provider, parent.model) if provider else None
    if model is None:
        return INHERIT, []
    fast = fast_options(model)
    if fast and not runnable(provider):
        reason = "; ".join(provider.get("constraints") or []) or "cannot run child tasks"
        raise RolesError(
            f"role {name!r} cannot inherit {parent.provider}/{parent.model}: "
            f"{parent.provider} is not runnable ({reason}), so {', '.join(fast)} cannot be pinned false, "
            f"and {EXCLUDED_RULE}"
        )
    reasons = []
    if BUDGETS[budget] is not None and effort_option(model) is not None and runnable(provider):
        reasons.append(f"the {budget} budget applies")
    if fast:
        reasons.append("fastMode stays false")
    if not reasons:
        return INHERIT, []
    seat = finish_seat(parent_seat, model, budget)
    return seat, [{"info": f"inherit made explicit as {parent.provider}/{parent.model} so {' and '.join(reasons)}"}]


def resolve_seat(seat, catalog, budget, name):
    """Return (resolved seat, notes, problems). Problems are seats the catalog rejects."""
    if seat == INHERIT:
        value, notes = _resolve_inherit(catalog, budget, name)
        return value, notes, []
    provider = providers_by_id(catalog).get(seat["providerInstanceId"])
    if not runnable(provider):
        reason = "; ".join(provider.get("constraints") or []) if provider else "not in catalog"
        note = f"{seat['providerInstanceId']} is not runnable ({reason}); seat inherits the parent"
        value, inherit_notes = _resolve_inherit(catalog, budget, name)
        return value, [note] + inherit_notes, [note]
    notes, problems = [], []
    model = find_model(provider, seat["model"])
    if model is None:
        model = _first_pickable(provider)
        if model is None:
            first = {"providerInstanceId": provider["providerInstanceId"], "model": models_of(provider)[0]["id"]}
            raise RolesError(excluded_refusal(name, first) or f"{provider['providerInstanceId']} has no model pstack may pick for {name!r}")
        note = f"{seat['providerInstanceId']}/{seat['model']} is not in the catalog; using {model['id']}"
        notes.append(note)
        problems.append(note)
        seat = {**seat, "providerInstanceId": provider["providerInstanceId"], "model": model["id"]}
    known = {option["id"] for option in options_of(model)}
    dropped = sorted(set(seat.get("options") or {}) - known)
    if dropped:
        note = f"dropped unknown options {', '.join(dropped)}"
        notes.append(note)
        problems.append(note)
    invalid = check_option_values(seat, model)
    problems.extend(invalid)
    notes.extend(f"dropped {problem}" for problem in invalid)
    bad = {problem.split("=", 1)[0].removeprefix("option ") for problem in invalid}
    options = {key: value for key, value in (seat.get("options") or {}).items() if key in known and key not in bad}
    seat = {key: value for key, value in seat.items() if key != "options"}
    if options:
        seat["options"] = options
    seat = finish_seat(seat, model, budget)
    return seat, notes, problems


def finish_seat(seat, model, budget):
    """Every explicit seat passes here, so an excluded id raises instead of being emitted."""
    if excluded_id(seat["model"]):
        raise RolesError(f"{seat['providerInstanceId']}/{seat['model']}: {excluded_reason(seat)}, and {EXCLUDED_RULE}")
    return apply_budget(without_fast(seat, model), model, budget)


def _seats_include_inherit(seats):
    if seats in (INHERIT, DEFAULT_PANEL):
        return True
    return isinstance(seats, list) and any(seat == INHERIT for seat in seats)


def settle_inherit_catalog(name, seats, catalog, parent):
    """When inherit needs a catalog to settle an excluded parent, report catalog-required."""
    if catalog is None and parent is not None and excluded_id(parent.model) and _seats_include_inherit(seats):
        if fast_grok(parent.model):
            lead = f"the parent {parent.provider}/{parent.model} is a fast Grok variant, so inherit needs the catalog"
        else:
            lead = (
                f"the parent {parent.provider}/{parent.model} is Claude Haiku 4.5, so inherit needs the catalog"
            )
        return CATALOG_REQUIRED, (
            f"{lead}: call orchestrator_capabilities and rerun roles.py show --catalog, "
            f"and {EXCLUDED_RULE}"
        )
    return seats, None


def _store_settled(entry, name, catalog, parent, budget):
    seats, note = settle_inherit_catalog(name, entry["seats"], catalog, parent)
    entry["seats"] = seats
    if note:
        entry["note"] = note


def runs_haiku_55(seat, parent):
    if seat == INHERIT:
        return parent is not None and normalized_bare(parent.model) == "claude-haiku-5-5"
    if isinstance(seat, dict):
        return normalized_bare(seat.get("model", "")) == "claude-haiku-5-5"
    return False


def attach_haiku_brief(entry, seats, parent):
    if isinstance(seats, list) and any(runs_haiku_55(seat, parent) for seat in seats):
        entry["haikuBrief"] = list(HAIKU_BRIEF)


def configured_seats(config, name):
    """Return configured seats without excluded seats and a note for each skip.

    Return None for seats when no configured seat remains.
    """
    seats = config["roles"].get(name)
    if seats is None:
        return None, []
    kept, notes = [], []
    for seat in seats:
        reason = excluded_reason(seat)
        if reason is None:
            kept.append(seat)
        else:
            notes.append(f"skipped configured seat {seat['providerInstanceId']}/{seat['model']}: {reason}, and {EXCLUDED_RULE}")
    return (kept or None), notes


def excluded_problems(roles):
    return [
        f"{name}: {seat['providerInstanceId']}/{seat['model']}: {reason}, and {EXCLUDED_RULE}"
        for name, seats in roles.items()
        for seat in seats
        if (reason := excluded_reason(seat))
    ]


def resolve(config, catalog=None, names=None, parent=None, providers=None, launches_seats=False):
    names = names or ROLES
    decision = config.get("mode", DEFAULT_MODE)
    budget = seat_budget(config["budget"], decision.mode)
    if catalog is not None:
        if parent is None:
            parent = inherit_parent(catalog)
        catalog = stamp_parent(catalog, parent)
    result = {
        "budget": config["budget"],
        "mode": decision.mode,
        "modeSource": decision.where,
        "escalate": config["escalate"] if "escalate" in config else None,
        "catalog": bool(catalog),
        "roles": {},
    }
    for name in names:
        if name not in ROLES:
            raise RolesError(f"unknown role {name!r}")
        configured, skipped = configured_seats(config, name)
        if configured is None and name == PANEL_BACKUP_ROLE and name in config["roles"]:
            configured = []
        entry = {"source": config["sources"].get(name, "default") if configured is not None else "default"}
        role_providers = providers if name == "skill tests" and providers is not None else None
        configured_cursor = (
            launches_seats
            and configured
            and isinstance(configured[0], dict)
            and configured[0]["providerInstanceId"] in CANNOT_LAUNCH_SEATS
        )
        if configured is None or (role_providers is not None and configured_cursor):
            selection = default_seats(name, catalog, budget, role_providers)
            if isinstance(selection.seats, str):
                entry["seats"] = selection.seats
                if skipped:
                    entry["notes"] = skipped
                if selection.notes:
                    entry["note"] = selection.notes[0]
                _store_settled(entry, name, catalog, parent, budget)
                attach_haiku_brief(entry, entry["seats"], parent)
                result["roles"][name] = entry
                continue
            seats = list(selection.seats)
            selection_notes = skipped + list(selection.notes)
        else:
            seats = configured
            selection_notes = skipped
        if name == PANEL_BACKUP_ROLE and catalog is None:
            entry["seats"] = CATALOG_REQUIRED
            entry["note"] = PANEL_CATALOG_NOTE
            if selection_notes:
                entry["notes"] = selection_notes
        elif catalog is None:
            entry["seats"] = seats
            if selection_notes:
                entry["notes"] = selection_notes
        elif name == PANEL_BACKUP_ROLE:
            verdicts = panel_verdicts(seats, catalog, budget)
            entry["seats"] = [verdict.seat for verdict in verdicts if verdict.seat is not None]
            panel_notes = selection_notes + [note for verdict in verdicts for note in verdict.notes]
            shortfall = panel_shortfall(entry["seats"])
            if shortfall is not None:
                panel_notes.append(shortfall)
            if panel_notes:
                entry["notes"] = panel_notes
        else:
            resolved, notes = [], []
            for seat in seats:
                value, seat_notes, _ = resolve_seat(seat, catalog, budget, name)
                if launches_seats and name == "skill tests" and launch_provider(value, parent) in CANNOT_LAUNCH_SEATS:
                    raise RolesError(launch_refusal(f"the seat resolved to {launch_provider(value, parent)}"))
                resolved.append(value)
                notes.extend(seat_notes)
            entry["seats"] = resolved
            info = [note["info"] for note in notes if isinstance(note, dict)]
            problems = selection_notes + [note for note in notes if not isinstance(note, dict)]
            if problems:
                entry["notes"] = problems
            if info:
                entry["info"] = info
        _store_settled(entry, name, catalog, parent, budget)
        attach_haiku_brief(entry, entry["seats"], parent)
        result["roles"][name] = entry
    return result


def usage_limited(text):
    return any(pattern.search(text or "") for pattern in USAGE_LIMIT_PATTERNS)


def seat_level(options):
    """The failed seat's level, from an effort id or variant. None when the seat named none."""
    if not isinstance(options, dict):
        return None
    for key in (*EFFORT_IDS, "variant"):
        value = options.get(key)
        if isinstance(value, str) and value in LADDER:
            return value
    return None


def author_families(authors):
    return {family(author) for author in authors or () if author}


def backup_ladder(role, failed_provider, authors, out):
    """Models to try, in order. An empty ladder parks.

    A worker parks only when claudeAgent is out. A Claude model on another provider still moves there.
    A review backups seat has no backup.
    """
    if role == PANEL_BACKUP_ROLE:
        return ()
    if role in REVIEW_ROLES:
        skip = author_families(authors)
        return tuple(model_id for model_id in REVIEW_LADDER if family(model_id) not in skip)
    if CLAUDE_BACKUP_PROVIDER == failed_provider or CLAUDE_BACKUP_PROVIDER in out:
        return ()
    if role in LIGHT_ROLES:
        return (LIGHT_BACKUP,)
    return (WORKER_BACKUP,)


def _catalog_pair(catalog, provider_id, model_id, blocked=frozenset()):
    if provider_id in blocked:
        return None
    provider = providers_by_id(catalog).get(provider_id)
    if not runnable(provider):
        return None
    model = find_model(provider, model_id)
    if model is None or not pickable(model_id):
        return None
    return provider, model


def _emit_backup(role, label, provider, model, source_options, budget, resumed):
    seat = {"providerInstanceId": provider["providerInstanceId"], "model": model["id"]}
    level = seat_level(source_options)
    if level is not None:
        seat = apply_level(seat, model, level)
    seat = finish_seat(seat, model, budget)
    applied = seat_level(seat.get("options"))
    where = f"{seat['providerInstanceId']}/{seat['model']}"
    at = f" at {applied}" if applied else ""
    if resumed:
        report = f"{role}: {label} resumed on {where}{at} after the reset"
    else:
        report = f"{role}: {label} hit its usage limit; relaunched on {where}{at}"
    return Backup("relaunch", report, seat)


@dataclass(frozen=True)
class PanelVerdict:
    """What backup does with one configured review backups seat.

    Exactly one of seat and reason is set. seat is resolve_seat's output for a
    pair _catalog_pair accepted, so it is never inherit and never a substituted model.
    """

    where: str
    seat: dict | None = None
    reason: str | None = None
    option_notes: tuple = ()
    option_problems: tuple = ()

    @property
    def notes(self):
        if self.reason is not None:
            return (f"dropped {self.where}: {self.reason}",)
        return tuple(f"{self.where}: {note}" for note in self.option_notes)

    @property
    def problems(self):
        if self.reason is not None:
            return self.notes
        return tuple(f"{self.where}: {problem}" for problem in self.option_problems)


def panel_verdicts(configured, catalog, budget, blocked=frozenset(), authors=()):
    """One verdict per configured review backups seat, in seat order.

    The caller removes excluded seats first. A seat is dropped for the first of
    these that holds: a Codex or Cursor provider, a blocked provider, an author's
    family, a provider that is not runnable or a model not in the catalog, a
    family an earlier kept seat has.
    """
    skip = author_families(authors)
    verdicts, seated = [], set()
    for seat in configured:
        provider_id, model_id = seat["providerInstanceId"], seat["model"]
        where = f"{provider_id}/{model_id}"
        seat_family = family(model_id)
        if provider_id in NEVER_BACKUP_PROVIDERS:
            reason = "backup never selects Codex or Cursor"
        elif provider_id in blocked:
            reason = f"{provider_id} is out"
        elif seat_family in skip:
            reason = f"{seat_family} wrote the diff"
        elif _catalog_pair(catalog, provider_id, model_id) is None:
            reason = "not runnable or not in the catalog"
        elif seat_family in seated:
            reason = f"family {seat_family} already seated"
        else:
            reason = None
        if reason is not None:
            verdicts.append(PanelVerdict(where, reason=reason))
            continue
        value, seat_notes, seat_problems = resolve_seat(seat, catalog, budget, PANEL_BACKUP_ROLE)
        seated.add(seat_family)
        verdicts.append(PanelVerdict(where, value, None, tuple(seat_notes), tuple(seat_problems)))
    return verdicts


def panel_shortfall(seats):
    """None when seats can run a panel, else the clause that says how far short they are."""
    if len(seats) >= PANEL_MINIMUM_PASSES:
        return None
    return f"has {len(seats)} usable seat{'' if len(seats) == 1 else 's'} and needs {PANEL_MINIMUM_PASSES}"


def _backup_panel(role, label, review_backups, catalog, budget, blocked, authors, resume):
    configured, skipped = review_backups
    verdicts = panel_verdicts(configured or [], catalog, budget, blocked, authors)
    seats = [verdict.seat for verdict in verdicts if verdict.seat is not None]
    notes = skipped + [note for verdict in verdicts for note in verdict.notes]
    lead = f"{role}: {label} is still out after the reset" if resume else f"{role}: {label} hit its usage limit"
    shortfall = panel_shortfall(seats)
    if shortfall is None:
        report = (
            f"{lead}; every paid reviewer backup is out, so review backups runs {len(seats)} seats; "
            "land only if no reviewer reproduces a blocker and at least two pass"
        )
        return Backup("panel", report, seats=tuple(seats), notes=tuple(notes))
    report = f"{lead}; review backups {shortfall}, so the work waits for the reset"
    if notes:
        report += f" ({'; '.join(notes)})"
    return Backup("park", report)


def backup_seat(role, failed, text, catalog, budget, out, authors, resume=False, review_backups=None):
    """Pick the one backup seat, a review backups panel, or park. The caller passes providers already out.

    With resume, the original seat comes back first when its provider is not out.
    review_backups is configured_seats' (seats, notes) for that role, or None when it is unset.
    """
    provider_id = failed["provider"]
    model_id = failed["model"]
    label = f"{provider_id}/{model_id}"
    out = set(out or ())
    blocked = NEVER_BACKUP_PROVIDERS | {provider_id} | out
    if resume:
        reviews_itself = role in AUTHOR_CHECKED_ROLES and family(model_id) in author_families(authors)
        if reviews_itself and role == PANEL_BACKUP_ROLE:
            report = f"{role}: {label} is in an author's family, so it does not resume and counts as no pass"
            return Backup("park", report)
        original = None if reviews_itself else _catalog_pair(catalog, provider_id, model_id, out)
        if original is not None:
            return _emit_backup(role, label, *original, failed.get("options"), budget, True)
    elif not usage_limited(text):
        report = f"{role}: {label} failed without a usage limit; respawn per Failure handling"
        return Backup("not-usage-limit", report)
    for wanted in backup_ladder(role, provider_id, authors, out):
        chosen = _catalog_pair(catalog, BACKUP_PROVIDERS[wanted], wanted, blocked)
        if chosen is not None:
            return _emit_backup(role, label, *chosen, failed.get("options"), budget, resume)
    if role == PANEL_BACKUP_ROLE:
        report = f"{role}: {label} hit its usage limit; a review backups seat has no backup, so it counts as no pass"
        return Backup("park", report)
    if role == PANEL_GATE_ROLE and review_backups is not None:
        return _backup_panel(role, label, review_backups, catalog, budget, blocked, authors, resume)
    if resume:
        report = f"{role}: {label} is still out after the reset; no backup seat, so the work waits for the reset"
    else:
        report = f"{role}: {label} hit its usage limit; no backup seat, so the work waits for the reset"
    return Backup("park", report)


def parse_applied_options(text):
    """Options from t3_thread_configuration, or a target's options object."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as error:
        raise RolesError(f"--options: invalid JSON: {error}") from error
    if isinstance(data, dict):
        return data
    if not isinstance(data, list):
        raise RolesError("--options must be a JSON object or an array of id and value")
    options = {}
    for item in data:
        if not isinstance(item, dict) or "id" not in item or "value" not in item:
            raise RolesError("--options array entries need id and value")
        options[item["id"]] = item["value"]
    return options


def command_backup(args):
    if args.catalog == "-":
        raise RolesError("--catalog - is refused because stdin carries the error text")
    given_parent(args)
    if args.provider == INHERIT:
        raise RolesError("backup refuses provider 'inherit'. Read the seat with t3_thread_configuration")
    if args.role not in ROLES:
        raise RolesError(f"unknown role {args.role!r}")
    authors = list(args.author or [])
    if args.role in REVIEW_ROLES and not authors:
        raise RolesError(f"role {args.role!r} needs --author, the model whose work it judges")
    if args.role == PANEL_BACKUP_ROLE and args.resume and not authors:
        raise RolesError(f"role {args.role!r} needs --author with --resume, the model whose work it judges")
    text = "" if args.resume else sys.stdin.read()
    config = merged_config(args.cwd, args.config, args.project_config)
    decision = effective_mode(config, args.brief_mode, args.session_mode, args.coordinator_mode)
    budget = seat_budget(config["budget"], decision.mode)
    _catalog_path, catalog = load_show_catalog(args)
    if catalog is None:
        raise RolesError("backup needs a catalog. Pass --catalog, or save one with setup-pstack")
    options = parse_applied_options(args.options) if args.options else {}
    failed = {"provider": args.provider, "model": args.model, "options": options}
    review_backups = configured_seats(config, PANEL_BACKUP_ROLE) if PANEL_BACKUP_ROLE in config["roles"] else None
    result = backup_seat(
        args.role, failed, text, catalog, budget, args.out or [], authors, args.resume, review_backups,
    )
    payload = {
        "decision": result.decision,
        "role": args.role,
        "failed": f"{args.provider}/{args.model}",
    }
    if result.seat is not None:
        payload["seat"] = result.seat
    if result.seats is not None:
        payload["seats"] = list(result.seats)
        payload["rule"] = PANEL_RULE
    if result.notes:
        payload["notes"] = list(result.notes)
    payload["report"] = result.report
    print(json.dumps(payload, indent=2))
    return 0


def write_atomic(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False, suffix=".tmp") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
    os.replace(handle.name, path)


def validate(config, catalog):
    problems = excluded_problems(config["roles"])
    for name, seats in config["roles"].items():
        seats = [seat for seat in seats if not excluded_reason(seat)]
        if name == PANEL_BACKUP_ROLE:
            verdicts = panel_verdicts(seats, catalog, config["budget"])
            problems.extend(f"{name}: {problem}" for verdict in verdicts for problem in verdict.problems)
            shortfall = panel_shortfall([verdict.seat for verdict in verdicts if verdict.seat is not None])
            if shortfall is not None:
                problems.append(f"{name}: {shortfall}")
            continue
        for seat in seats:
            _, _, seat_problems = resolve_seat(seat, catalog, config["budget"], name)
            problems.extend(f"{name}: {problem}" for problem in seat_problems)
    return problems


def load_show_catalog(args):
    if args.catalog:
        return args.catalog, load_catalog(args.catalog)
    path = snapshot_path()
    if path.is_file():
        return path, load_catalog(path)
    return None, None


def catalog_for_check(args, catalog, catalog_path):
    """Parent for this invocation, and a catalog copy whose inherited keys match it."""
    parent = parent_for(args, catalog, catalog_path)
    if catalog is None:
        return parent, None
    return parent, stamp_parent(catalog, parent)


def command_show(args):
    given_parent(args)
    mode = given_runtime_mode(args)
    config = merged_config(args.cwd, args.config, args.project_config)
    decision = effective_mode(config, args.brief_mode, args.session_mode, args.coordinator_mode)
    config["mode"] = decision
    catalog_path, catalog = load_show_catalog(args)
    parent, catalog = catalog_for_check(args, catalog, catalog_path)
    catalog = for_runtime_mode(catalog, mode)
    launches = getattr(args, "launches_seats", False)
    if launches:
        roles = args.role or []
        if roles != ["skill tests"]:
            raise RolesError('--launches-seats is valid only with exactly one --role "skill tests"')
        if catalog is None:
            raise RolesError("--launches-seats requires a catalog")
        if args.parent is None:
            raise RolesError("--launches-seats requires --parent")
        pool = launch_providers(config, catalog, parent)
        payload = resolve(config, catalog, args.role, parent, providers=pool, launches_seats=True)
    else:
        payload = resolve(config, catalog, args.role, parent)
    print(json.dumps(payload, indent=2))
    line = light_cap_gap(decision, config["budget"], catalog is not None, args.parent is not None)
    if line:
        print(line, file=sys.stderr)


def command_validate(args):
    given_parent(args)
    config = merged_config(args.cwd, args.config, args.project_config)
    catalog = load_catalog(args.catalog)
    _parent, catalog = catalog_for_check(args, catalog, args.catalog)
    problems = validate(config, catalog)
    for problem in problems:
        print(problem)
    if not problems:
        print("ok")
    return 1 if problems else 0


def command_write(args):
    given_parent(args)
    catalog = load_catalog(args.catalog)
    target = project_config_path(args.cwd) if args.project else (Path(args.config) if args.config else user_config_path())
    try:
        loaded = load_json(target)
    except RolesError:
        if args.keep:
            raise
        loaded = None
    if loaded is None:
        loaded = {}
    if args.keep:
        raw = check_shape(loaded, target)
    elif isinstance(loaded, dict):
        raw = loaded
    else:
        raw = {}
    # Budget and roles survive a rewrite only with --keep. Escalate is separate.
    existing = raw if args.keep else {}
    roles = dict(existing.get("roles", {}))
    for assignment in args.set or []:
        name, equals, value = assignment.partition("=")
        name = name.strip()
        if not equals or name not in ROLES:
            raise RolesError(f"--set {assignment!r}: expected '<role>=<seat>[;<seat>...]' with a known role")
        roles[name] = [parse_seat(part) for part in value.split(";") if part.strip()]
    config = {"version": 1, "roles": roles}
    budget = args.budget or existing.get("budget")
    if budget is not None:
        config["budget"] = budget
    elif not args.project:
        config["budget"] = "default"
    if args.mode:
        config["mode"] = args.mode
    elif args.keep and "mode" in raw:
        config["mode"] = raw["mode"]
    elif not args.project:
        config["mode"] = "full"
    if args.project and not args.clear_escalate:
        if args.escalate is not None:
            config["escalate"] = list(args.escalate)
        elif "escalate" in raw:
            config["escalate"] = raw["escalate"]
    check_shape(config, target)
    if "escalate" in config:
        config["escalate"] = list(config["escalate"])
    excluded = excluded_problems(roles)
    if excluded:
        raise RolesError("refusing to write, even with --force:\n" + "\n".join(excluded))
    _parent, checking = catalog_for_check(args, catalog, args.catalog)
    problems = validate({"budget": config.get("budget", "default"), "roles": roles, "sources": {}}, checking)
    if problems and not args.force:
        raise RolesError("refusing to write without --force:\n" + "\n".join(problems))
    write_atomic(target, config)
    if not args.project and not args.config:
        write_atomic(snapshot_path(), catalog)
    print(f"wrote {target}")


def launch_refusal(detail):
    return (
        f"role 'skill tests' has no seat for a child that launches seats: "
        f"{', '.join(sorted(CANNOT_LAUNCH_SEATS))} cannot launch seats, and {detail}"
    )


def launch_providers(config, catalog, parent):
    """Providers a child that launches seats may run on.

    The configured single-role seats, else the runnable providers that serve a built-in default
    family plus the parent's provider. Cursor never joins, because it cannot launch seats.
    """
    configured = {
        seat["providerInstanceId"]
        for name in SINGLE_ROLES
        for seat in config["roles"].get(name) or []
        if isinstance(seat, dict)
    } - CANNOT_LAUNCH_SEATS
    if configured:
        return configured
    defaults = {
        provider["providerInstanceId"]
        for provider in catalog["providers"]
        if runnable(provider)
        and any(family(model["id"]) in DEFAULT_FAMILIES and pickable(model["id"]) for model in models_of(provider))
    }
    allowed = (defaults | ({parent.provider} if parent else set())) - CANNOT_LAUNCH_SEATS
    if not allowed:
        raise RolesError(launch_refusal(
            "no single-role seat in roles.json, built-in default family, or parent names another provider"
        ))
    return allowed


def launch_provider(seat, parent):
    if seat == INHERIT:
        return parent.provider
    return seat["providerInstanceId"]


def persona_path():
    return Path(__file__).resolve().parents[1] / "agents" / "poteto-agent.md"


def playbook_stems():
    root = Path(__file__).resolve().parents[2]
    rendered_tree = root / "poteto-mode" / "playbooks"
    source_checkout = root / "skills" / "poteto-mode" / "playbooks"
    candidates = (rendered_tree, source_checkout)
    directory = next((candidate for candidate in candidates if candidate.is_dir()), None)
    if directory is None:
        raise RolesError("no playbook directory: " + ", ".join(str(candidate) for candidate in candidates))
    stems = frozenset(
        entry.stem for entry in directory.iterdir() if entry.is_file() and entry.suffix == ".md"
    )
    if not stems:
        raise RolesError(f"{directory}: playbook directory is empty")
    return stems


def load_brief_rules():
    path = persona_path()
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise RolesError(f"{path}: persona not found") from error
    except UnicodeDecodeError as error:
        raise RolesError(f"{path}: persona is not valid UTF-8") from error
    except OSError as error:
        raise RolesError(f"{path}: cannot read persona: {error.strerror}") from error
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        raise RolesError(f"{path}: persona file has no frontmatter")
    fences = [index for index, line in enumerate(lines) if line.strip() == "---"]
    if len(fences) < 2:
        raise RolesError(f"{path}: persona file has no frontmatter")
    body = "".join(lines[fences[1] + 1:]).strip()
    if not body:
        raise RolesError(f"{path}: persona body is empty")
    return body, playbook_stems()


def playbook_values(text):
    values = []
    for line in text.splitlines():
        match = re.fullmatch(r"Playbook:\s*(\S+)\s*", line)
        if match:
            values.append(match.group(1))
    return values


def playbook_stem(value):
    prefix = "playbooks/"
    suffix = ".md"
    if not value.startswith(prefix) or not value.endswith(suffix):
        return None
    stem = value[len(prefix):-len(suffix)]
    if not stem or "/" in stem or stem in (".", ".."):
        return None
    return stem


def brief_problems(text, persona_body, playbooks):
    problems = []
    collapsed_body = " ".join(persona_body.split())
    collapsed_brief = " ".join(text.split())
    if not collapsed_brief.startswith(collapsed_body):
        problems.append(
            f"missing persona: open the brief with the body of {persona_path()}, without its frontmatter"
        )
    names = ", ".join(sorted(playbooks))
    values = playbook_values(text)
    stem = None
    if not values:
        problems.append(
            "missing playbook: add one line 'Playbook: playbooks/<name>.md', where <name> is one of: " + names
        )
    elif len(values) > 1:
        problems.append("more than one Playbook line: keep one")
    else:
        candidate = playbook_stem(values[0])
        if candidate in playbooks:
            stem = candidate
        else:
            problems.append(f"unknown playbook '{values[0]}': expected one of: {names}")
    problems.extend(mode_problems(text, stem))
    return problems


def segments_match(pattern, path):
    """Whole-segment glob. ** matches zero or more segments. Other segments never cross a slash."""

    def match(pattern_parts, path_parts):
        if not pattern_parts:
            return not path_parts
        if pattern_parts[0] == "**":
            return any(match(pattern_parts[1:], path_parts[index:]) for index in range(len(path_parts) + 1))
        return (
            bool(path_parts)
            and fnmatch.fnmatchcase(path_parts[0], pattern_parts[0])
            and match(pattern_parts[1:], path_parts[1:])
        )

    pattern_parts = [] if pattern == "" else pattern.split("/")
    path_parts = [] if path == "" else path.split("/")
    return match(pattern_parts, path_parts)


def escalated_path(leases, patterns, tracked):
    """First covered path that matches a pattern. Candidates are sorted, so pattern order does not matter."""
    covered = set()
    for lease in leases:
        if lease == "":
            covered.update(tracked)
            continue
        covered.add(lease)
        prefix = lease + "/"
        covered.update(path for path in tracked if path.startswith(prefix))
    for path in sorted(covered):
        if any(segments_match(pattern, path) for pattern in patterns):
            return path
    return None


def tracked_files(cwd):
    """Repository-relative tracked paths. Any git failure means cwd is not a checkout."""
    message = f"--paths needs a git checkout to list tracked files, and {cwd} is not one"

    def git(args):
        try:
            return subprocess.run(args, capture_output=True)
        except OSError as error:
            raise RolesError(message) from error

    top = git(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"])
    lines = top.stdout.decode("utf-8", "surrogateescape").splitlines()
    if top.returncode != 0 or not lines:
        raise RolesError(message)
    listing = git(["git", "-C", lines[0], "ls-files", "-z"])
    if listing.returncode != 0:
        raise RolesError(message)
    parts = listing.stdout.decode("utf-8", "surrogateescape").split("\0")
    if parts and parts[-1] == "":
        del parts[-1]
    return parts


def escalation_reason(durable, hit, send_backs):
    """Durable reason first, then a covered path, then a second send-back."""
    if durable is not None:
        return durable
    if hit is not None:
        return f"lease covers {hit}"
    if send_backs >= 2:
        return "second send-back"
    return None


def escalate(decision, reason):
    """Escalation only moves toward full."""
    if reason is None:
        return decision
    label = f"escalated: {reason}"
    return ModeDecision("full", label, label)


class Waivers(dict):
    """Map (playbook stem, attempt kind) to waived step names, in table order.

    A missing playbook with a known attempt waives nothing. An unknown attempt kind is a KeyError.
    """

    def __missing__(self, key):
        if isinstance(key, tuple) and len(key) == 2 and key[1] in ATTEMPTS:
            return ()
        raise KeyError(key)


_WAIVER_ROWS = {
    "feature": (
        ("Arena", "Interrogate", "Comment Sicko"),
        ("How", "Architect", "Arena", "Interrogate", "Comment Sicko"),
    ),
    "bug-fix": (("Comment Sicko",), ("How", "Why", "Architect", "Comment Sicko")),
    "refactoring": (("Comment Sicko",), ("How", "Architect", "Comment Sicko")),
    "perf-issue": (("Comment Sicko",), ("How", "Architect", "Comment Sicko")),
    "hillclimb": (("Comment Sicko",), ("How", "Comment Sicko")),
    "authoring-a-skill": (
        ("Comment Sicko", "Second-provider test"),
        ("Comment Sicko", "Second-provider test"),
    ),
}
LIGHT_WAIVERS = Waivers({
    (playbook, attempt): first if attempt == "first" else retry
    for playbook, (first, retry) in _WAIVER_ROWS.items()
    for attempt in ATTEMPTS
})


def durable_reason(text):
    if text is None:
        return None
    if text.strip() == "" or "\n" in text or "\r" in text:
        raise ModeSettingsError("--escalated needs a one-line reason")
    return text.strip()


# The colon sits in the match so "Mode source" is not a "Mode" line.
GRAMMAR_LABELS = ("Mode", "Mode source", "Attempt", "Waived by mode", "Gate")
_GRAMMAR_LINE = re.compile("(" + "|".join(map(re.escape, GRAMMAR_LABELS)) + r"):(.*)")


def waived_value(mode, key):
    """Waiver text for one item, or None when the brief carries no such line.

    Full mode returns None and does not read key. An empty light tuple is None.
    """
    if mode != "light":
        return None
    return ", ".join(LIGHT_WAIVERS[key]) or None


def brief_lines(decision, key):
    """Playbook, Mode, Mode source, Attempt, and Waived by mode, each when it applies."""
    lines = [] if key is None else [f"Playbook: playbooks/{key[0]}.md"]
    lines.append(f"Mode: {decision.mode}")
    lines.append(f"Mode source: {decision.label}")
    if key is not None:
        lines.append(f"Attempt: {key[1]}")
        value = waived_value(decision.mode, key)
        if value is not None:
            lines.append(f"Waived by mode: {value}")
    return lines


def _grammar_lines(text):
    """Label to stripped values, in brief order."""
    found = {label: [] for label in GRAMMAR_LABELS}
    for line in text.splitlines():
        match = _GRAMMAR_LINE.fullmatch(line)
        if match:
            found[match.group(1)].append(match.group(2).strip())
    return found


def _waiver_problem(mode, key, expected, actual):
    if expected is None:
        if mode == "full":
            return "unexpected Waived by mode line: Mode: full waives nothing, remove it"
        return (
            f"unexpected Waived by mode line: playbooks/{key[0]}.md "
            f"waives nothing on attempt {key[1]}, remove it"
        )
    if actual is None:
        return f"missing Waived by mode line: add 'Waived by mode: {expected}'"
    return f"wrong Waived by mode line: expected 'Waived by mode: {expected}'"


MISSING_MODE = (
    "missing Mode: paste the lines 'roles.py mode --playbook <name> --attempt <kind>' prints, "
    "which include one line 'Mode: full' or 'Mode: light'"
)


def mode_problems(text, stem):
    lines = _grammar_lines(text)
    if not lines["Mode"]:
        return [MISSING_MODE]
    problems = [
        f"more than one {label} line: keep one"
        for label in GRAMMAR_LABELS
        if len(lines[label]) > 1
    ]
    if len(lines["Mode"]) > 1:
        return problems
    mode = lines["Mode"][0]
    if mode not in MODES:
        problems.append(f"bad Mode value '{mode}': expected {' or '.join(MODES)}")
        return problems

    attempt = None
    attempts = lines["Attempt"]
    if len(attempts) == 1:
        if attempts[0] in ATTEMPTS:
            attempt = attempts[0]
        else:
            problems.append(
                f"bad Attempt value '{attempts[0]}': expected one of: {', '.join(ATTEMPTS)}"
            )
    elif not attempts and mode == "light":
        problems.append(
            "missing Attempt: Mode: light needs one line 'Attempt: <kind>', "
            f"where <kind> is one of: {', '.join(ATTEMPTS)}"
        )

    waived = lines["Waived by mode"]
    if len(waived) > 1:
        return problems
    if mode == "light" and (stem is None or attempt is None):
        return problems
    key = None if mode == "full" else (stem, attempt)
    expected = waived_value(mode, key)
    actual = waived[0] if waived else None
    if actual != expected:
        problems.append(_waiver_problem(mode, key, expected, actual))
    return problems


def work_key(playbook, attempt):
    if (playbook is None) != (attempt is None):
        raise ModeSettingsError("--playbook and --attempt go together: pass both or neither")
    if playbook is None:
        return None
    stems = playbook_stems()
    if playbook not in stems:
        names = ", ".join(sorted(stems))
        raise ModeSettingsError(f"unknown playbook '{playbook}': expected one of: {names}")
    return (playbook, attempt)


def command_mode(args):
    config = merged_config(args.cwd, args.config, args.project_config)
    decision = effective_mode(config, args.brief_mode, args.session_mode, args.coordinator_mode)
    key = work_key(args.playbook, args.attempt)
    durable = durable_reason(args.escalated)
    leases = lease_paths(args.paths) if args.paths is not None else []
    patterns = [canonical(item) for item in (config["escalate"] or [])]
    hit = escalated_path(leases, patterns, tracked_files(args.cwd)) if leases and patterns else None
    print("\n".join(brief_lines(escalate(decision, escalation_reason(durable, hit, args.send_backs)), key)))


def command_check_brief(args):
    path = Path(args.brief)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as error:
        raise RolesError(f"{path}: brief not found") from error
    except UnicodeDecodeError as error:
        raise RolesError(f"{path}: brief is not valid UTF-8") from error
    except OSError as error:
        raise RolesError(f"{path}: cannot read brief: {error.strerror}") from error
    persona_body, playbooks = load_brief_rules()
    problems = brief_problems(text, persona_body, playbooks)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    stem = playbook_stem(playbook_values(text)[0])
    print(f"ok playbooks/{stem}.md")
    return 0


def non_negative_int(text):
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid non-negative int value: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError(f"invalid non-negative int value: {text!r}")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("show", "validate", "write"):
        command = sub.add_parser(name)
        command.add_argument("--cwd", default=os.getcwd())
        command.add_argument("--config", help="user roles file (default ~/.config/pstack-t3/roles.json)")
        if name != "write":
            command.add_argument("--project-config", help="project roles file (default <repo>/.pstack/t3-roles.json)")
        command.add_argument("--catalog", required=name != "show", help="saved orchestrator_capabilities JSON, or - for stdin")
        command.add_argument("--parent", help="this thread's provider/model from orchestrator_capabilities (inheritedProviderInstanceId/inheritedModel)")
    sub.choices["show"].add_argument("--role", action="append")
    sub.choices["show"].add_argument(
        "--launches-seats",
        action="store_true",
        help="resolve skill tests for a child that launches seats (requires --catalog, --parent, and --role \"skill tests\")",
    )
    sub.choices["show"].add_argument(
        "--runtime-mode",
        help="this thread's runtimeMode from orchestrator_capabilities. With a catalog, a provider whose "
             "driverKind is muse counts as not runnable under a mode other than approval-required and full-access",
    )
    write = sub.choices["write"]
    write.add_argument("--budget", choices=list(BUDGETS))
    write.add_argument("--mode", choices=MODES)
    group = write.add_mutually_exclusive_group()
    # None means the flag was omitted. An empty list would replace a stored project list.
    group.add_argument("--escalate", action="append", default=None)
    group.add_argument("--clear-escalate", action="store_true")
    write.add_argument("--set", action="append", help="'<role>=<seat>[;<seat>]', seat = inherit | provider/model[?option=value]")
    write.add_argument("--project", action="store_true", help="write the project file instead of the user file")
    write.add_argument("--keep", action="store_true", help="keep roles already in the target file")
    write.add_argument("--force", action="store_true", help="write despite the problems validate lists, except an excluded seat")
    mode = sub.add_parser("mode")
    mode.add_argument("--cwd", default=os.getcwd())
    mode.add_argument("--config", help="user roles file (default ~/.config/pstack-t3/roles.json)")
    mode.add_argument("--project-config", help="project roles file (default <repo>/.pstack/t3-roles.json)")
    mode.add_argument("--paths", help="comma-separated leases")
    mode.add_argument("--send-backs", type=non_negative_int, default=0,
                      help="send-back count; 2 or more forces full mode")
    mode.add_argument("--escalated",
                      help="recorded one-line escalation reason; forces full mode and wins over paths and send-backs")
    mode.add_argument("--playbook", help="playbook stem, such as bug-fix")
    mode.add_argument("--attempt", choices=ATTEMPTS)
    check_brief = sub.add_parser("check-brief")
    check_brief.add_argument("brief", help="brief file to check")
    backup = sub.add_parser("backup")
    backup.add_argument("--cwd", default=os.getcwd())
    backup.add_argument("--config", help="user roles file (default ~/.config/pstack-t3/roles.json)")
    backup.add_argument("--project-config", help="project roles file (default <repo>/.pstack/t3-roles.json)")
    backup.add_argument("--catalog", help="saved orchestrator_capabilities JSON. Stdin is the error text, so - is refused")
    backup.add_argument("--parent", help="this thread's provider/model from orchestrator_capabilities (inheritedProviderInstanceId/inheritedModel)")
    backup.add_argument("--role", required=True)
    backup.add_argument("--provider", required=True)
    backup.add_argument("--model", required=True)
    backup.add_argument("--options", help="JSON options array from t3_thread_configuration, or a target options object")
    backup.add_argument(
        "--author", action="append", default=None,
        help="author model, or provider/model. Repeat for each model that wrote the diff. Required for a reviewer role",
    )
    backup.add_argument("--out", action="append", default=None, help="provider already out. Repeat for each")
    backup.add_argument("--resume", action="store_true", help="after a parked item's reset, print the seat to launch")
    for command in (sub.choices["show"], mode, backup):
        command.add_argument("--brief-mode", choices=MODES,
                             help="brief mode; overrides session, coordinator, project, and user modes")
        command.add_argument("--session-mode", choices=MODES,
                             help="session mode; used after brief and before coordinator, project, and user modes")
        command.add_argument("--coordinator-mode", choices=MODES,
                             help="coordinator mode; used after brief and session, before project and user modes")
    args = parser.parse_args(argv)
    if args.command == "write" and not args.project and (args.escalate is not None or args.clear_escalate):
        parser.error("--escalate and --clear-escalate require --project")
    try:
        return {
            "show": command_show,
            "validate": command_validate,
            "write": command_write,
            "check-brief": command_check_brief,
            "mode": command_mode,
            "backup": command_backup,
        }[args.command](args) or 0
    except ModeSettingsError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except RolesError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
