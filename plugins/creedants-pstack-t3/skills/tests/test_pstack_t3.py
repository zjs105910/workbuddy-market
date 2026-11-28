import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "t3/scripts"))
sys.path.insert(0, str(ROOT / "scripts"))

import check  # noqa: E402
import roles  # noqa: E402

CATALOG = json.loads((ROOT / "tests/fixtures/catalog.json").read_text())


def config(budget="default", **assigned):
    return {"budget": budget, "roles": assigned, "sources": {name: "test" for name in assigned}}


GROK_SEAT = {"providerInstanceId": "grok", "model": "grok-4.7", "options": {"reasoningEffort": "xhigh"}}
OPUS_SEAT = {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5", "options": {"effort": "xhigh"}}
CODE_ROLES = (
    "feature, refactoring", "bug-fix", "perf-issue", "hillclimb",
    "swarm workers", "reflect tooling",
)
HAIKU_READING_ROLES = ("how explorer", "why investigators")
HAIKU_READING_SEAT = {
    "providerInstanceId": "claudeAgent",
    "model": "claude-haiku-5-5",
    "options": {"effort": "medium"},
}
JUDGMENT_ROLES = (
    "judgment and prose", "hardest tasks", "how explainer", "why synthesizer",
    "reflect judgment, divergent, synthesizer",
)
PANEL_ROLES = ("arena runners", "arena cross-judge pool", "architect runners", "interrogate reviewers")


class RolesTest(unittest.TestCase):
    def test_fixture_defaults_are_grok_for_code_and_opus_for_judgment(self):
        for name in CODE_ROLES:
            entry = roles.resolve(config(), CATALOG, [name])["roles"][name]
            self.assertEqual(entry["seats"], [GROK_SEAT], name)
            self.assertNotIn("notes", entry, name)
        for name in HAIKU_READING_ROLES:
            entry = roles.resolve(config(), CATALOG, [name])["roles"][name]
            self.assertEqual(entry["seats"], [HAIKU_READING_SEAT], name)
            self.assertEqual(entry["haikuBrief"], list(roles.HAIKU_BRIEF), name)
        for name in JUDGMENT_ROLES:
            entry = roles.resolve(config(), CATALOG, [name])["roles"][name]
            self.assertEqual(entry["seats"], [OPUS_SEAT], name)
            self.assertNotIn("notes", entry, name)
        for name in PANEL_ROLES:
            entry = roles.resolve(config(), CATALOG, [name])["roles"][name]
            self.assertEqual(entry["seats"], [OPUS_SEAT, GROK_SEAT], name)
            self.assertNotIn("notes", entry, name)

    def test_every_role_has_one_default_policy(self):
        self.assertEqual(set(roles.ROLE_DEFAULTS), set(roles.ROLES))
        for name in roles.SINGLE_ROLES:
            policy = roles.ROLE_DEFAULTS[name]
            self.assertEqual(len(policy), 1)
        for name in roles.PANEL_ROLES:
            policy = roles.ROLE_DEFAULTS[name]
            if name == "verifiers":
                self.assertIs(policy, roles.AdaptiveDefault.VERIFIERS)
            elif name == "review backups":
                self.assertIs(policy, roles.AdaptiveDefault.UNSET)
            else:
                self.assertEqual(len(policy), 2)

    def test_setup_examples_match_resolved_fixture_defaults(self):
        text = (ROOT / "t3/setup.md").read_text()
        examples = re.findall(r'--set "([^"]+)"', text)
        self.assertEqual(examples, [
            "judgment and prose=claudeAgent/claude-opus-5-5?effort=xhigh",
            "swarm workers=grok/grok-4.7?reasoningEffort=xhigh",
            "interrogate reviewers=claudeAgent/claude-opus-5-5?effort=xhigh;grok/grok-4.7?reasoningEffort=xhigh",
        ])
        for example in examples:
            name, value = example.split("=", 1)
            expected = [roles.parse_seat(part) for part in value.split(";")]
            entry = roles.resolve(config(), CATALOG, [name])["roles"][name]
            self.assertEqual(entry["seats"], expected, name)
            self.assertNotIn("notes", entry, name)

    def test_show_prints_the_builtin_bug_fix_seat(self):
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "XDG_CONFIG_HOME": directory}
            completed = subprocess.run(
                [sys.executable, str(ROOT / "t3/scripts/roles.py"), "show", "--cwd", directory,
                 "--catalog", str(ROOT / "tests/fixtures/catalog.json"), "--role", "bug-fix",
                 "--parent", "claudeAgent/claude-opus-5-5"],
                env=env, capture_output=True, text=True, check=True)
        entry = json.loads(completed.stdout)["roles"]["bug-fix"]
        self.assertEqual(entry["seats"], [GROK_SEAT])
        self.assertEqual(entry["source"], "default")

    def test_preferred_seat_matching_the_parent_stays_explicit(self):
        catalog = {**CATALOG, "inheritedProviderInstanceId": "grok", "inheritedModel": "grok-4.7"}
        entry = roles.resolve(config(), catalog, ["bug-fix"])["roles"]["bug-fix"]
        self.assertEqual(entry["seats"], [GROK_SEAT])
        self.assertNotIn("notes", entry)

    def test_skill_tests_default_is_haiku_high(self):
        entry = roles.resolve(config(), CATALOG, ["skill tests"])["roles"]["skill tests"]
        self.assertEqual(entry["source"], "default")
        self.assertEqual(entry["seats"], [{"providerInstanceId": "claudeAgent", "model": "claude-haiku-5-5", "options": {"effort": "high"}}])
        self.assertEqual(entry["haikuBrief"], list(roles.HAIKU_BRIEF))

    def test_skill_tests_small_budget_lowers_haiku_effort(self):
        seats = roles.resolve(config("small"), CATALOG, ["skill tests"])["roles"]["skill tests"]["seats"]
        self.assertEqual(seats, [{"providerInstanceId": "claudeAgent", "model": "claude-haiku-5-5", "options": {"effort": "medium"}}])

    def test_skill_tests_without_a_catalog_reports_catalog_required(self):
        plain = roles.resolve(config(), None, ["skill tests"])["roles"]["skill tests"]
        self.assertEqual(plain["seats"], "catalog-required")
        self.assertIn("call orchestrator_capabilities", plain.get("note", ""))

    def test_runtime_role_table_lists_the_same_names_as_the_role_list(self):
        text = (ROOT / "t3/runtime.md").read_text()
        section = text.split("### Role names", 1)[1].split("### Built-in defaults", 1)[0]
        names = re.findall(r"\| `([^`]+)` \|", section)
        self.assertEqual(sorted(names), sorted(roles.ROLES))
        self.assertEqual(len(names), len(set(names)))
        proposals = (ROOT / "t3/setup.md").read_text().split("**(b) Propose roles.**", 1)[1].split("**(c) Confirm.**", 1)[0]
        self.assertIn("`skill tests`", proposals)

    def test_setup_proposes_review_backups_only_when_the_user_names_a_panel(self):
        text = (ROOT / "t3/setup.md").read_text()
        proposals = text.split("**(b) Propose roles.**", 1)[1].split("**(c) Confirm.**", 1)[0]
        for phrase in (
            "`review backups` is optional and has no built-in seats.",
            "Leave it unset unless the user names a panel.",
            "When set, a `verifiers` seat whose paid backups are all out runs that panel instead of parking.",
            "Never propose a Cursor, Codex, or `inherit` seat for it.",
        ):
            self.assertIn(phrase, proposals)
        self.assertNotIn("opencode", text)
        self.assertNotIn("opencode", (ROOT / "t3/runtime.md").read_text())

    def test_review_backups_is_unset_by_default(self):
        for catalog in (None, CATALOG):
            entry = roles.resolve(config(), catalog, ["review backups"])["roles"]["review backups"]
            self.assertEqual(entry, {"source": "default", "seats": "unset", "note": roles.UNSET_NOTE})

    def test_panel_default_is_one_seat_per_runnable_provider_with_parent_inheriting(self):
        seats = roles.resolve(config(), CATALOG, ["verifiers"])["roles"]["verifiers"]["seats"]
        self.assertEqual(seats, [
            "inherit",
            {"providerInstanceId": "codex", "model": "gpt-6.1-sol"},
            {"providerInstanceId": "grok", "model": "grok-4.7"},
        ])

    def test_panel_skips_a_provider_serving_a_family_already_seated(self):
        cursor = {"providerInstanceId": "cursor", "canRunChildTask": True, "constraints": [],
                  "models": [{"id": "claude-opus-5-5", "options": None}]}
        catalog = {**CATALOG, "providers": CATALOG["providers"] + [cursor]}
        seats = roles.resolve(config(), catalog, ["verifiers"])["roles"]["verifiers"]["seats"]
        self.assertNotIn({"providerInstanceId": "cursor", "model": "claude-opus-5-5"}, seats)
        self.assertEqual(len(seats), 3)

    def test_null_model_options_are_treated_as_none(self):
        provider = {"providerInstanceId": "pi", "canRunChildTask": True, "constraints": [], "models": [{"id": "pi-1", "options": None}]}
        catalog = {**CATALOG, "providers": CATALOG["providers"] + [provider]}
        entry = roles.resolve(config("large", **{"bug-fix": [{"providerInstanceId": "pi", "model": "pi-1"}]}), catalog, ["bug-fix"])["roles"]["bug-fix"]
        self.assertEqual(entry["seats"], [{"providerInstanceId": "pi", "model": "pi-1"}])

    def test_validate_rejects_option_values_the_catalog_lacks(self):
        seat = {"providerInstanceId": "codex", "model": "gpt-6.1-sol", "options": {"reasoningEffort": "banana", "serviceTier": True}}
        problems = roles.validate(config(**{"bug-fix": [seat]}), CATALOG)
        self.assertEqual(len(problems), 2, problems)

    def test_budget_makes_inherit_explicit_so_the_cap_applies(self):
        seats = roles.resolve(config("small", **{"bug-fix": ["inherit"]}), CATALOG, ["bug-fix"])["roles"]["bug-fix"]["seats"]
        self.assertEqual(seats, [{"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5", "options": {"effort": "medium"}}])
        entry = roles.resolve(config("small", **{"bug-fix": ["inherit"]}), CATALOG, ["bug-fix"])["roles"]["bug-fix"]
        self.assertNotIn("notes", entry)
        self.assertIn("inherit made explicit", entry["info"][0])
        plain = roles.resolve(config(), CATALOG, ["bug-fix"])["roles"]["bug-fix"]["seats"]
        self.assertEqual(plain, [GROK_SEAT])
        capped = roles.resolve(config("small"), CATALOG, ["bug-fix"])["roles"]["bug-fix"]["seats"]
        self.assertEqual(capped, [{"providerInstanceId": "grok", "model": "grok-4.7", "options": {"reasoningEffort": "medium"}}])

    def test_unlimited_budget_raises_builtin_seats_to_the_highest_non_special_level(self):
        grok = roles.resolve(config("unlimited"), CATALOG, ["bug-fix"])["roles"]["bug-fix"]["seats"]
        self.assertEqual(grok, [GROK_SEAT])
        opus_max = {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5", "options": {"effort": "max"}}
        judgment = roles.resolve(config("unlimited"), CATALOG, ["judgment and prose"])["roles"]["judgment and prose"]["seats"]
        self.assertEqual(judgment, [opus_max])
        panel = roles.resolve(config("unlimited"), CATALOG, ["interrogate reviewers"])["roles"]["interrogate reviewers"]["seats"]
        self.assertEqual(panel, [opus_max, GROK_SEAT])
        verifiers = roles.resolve(config("unlimited"), CATALOG, ["verifiers"])["roles"]["verifiers"]["seats"]
        self.assertEqual(verifiers[0], opus_max)
        self.assertEqual(verifiers[2]["options"]["reasoningEffort"], "xhigh")
        named = {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5", "options": {"effort": "xhigh"}}
        kept = roles.resolve(config("unlimited", **{"judgment and prose": [named]}), CATALOG, ["judgment and prose"])["roles"]["judgment and prose"]["seats"]
        self.assertEqual(kept, [named])

    def test_unlimited_with_no_grok_stops_at_max_on_a_codex_parent(self):
        providers = [provider for provider in CATALOG["providers"] if provider["providerInstanceId"] != "grok"]
        catalog = {
            **CATALOG,
            "providers": providers,
            "inheritedProviderInstanceId": "codex",
            "inheritedModel": "gpt-6.1-sol",
        }
        codex_max = {"providerInstanceId": "codex", "model": "gpt-6.1-sol", "options": {"reasoningEffort": "max"}}
        for name in CODE_ROLES:
            seats = roles.resolve(config("unlimited"), catalog, [name])["roles"][name]["seats"]
            self.assertEqual(seats, [codex_max], name)
        panel = roles.resolve(config("unlimited"), catalog, ["interrogate reviewers"])["roles"]["interrogate reviewers"]["seats"]
        self.assertEqual(panel[1], codex_max)
        explicit = {"providerInstanceId": "codex", "model": "gpt-6.1-sol", "options": {"reasoningEffort": "ultra"}}
        capped = roles.resolve(config("unlimited", **{"bug-fix": [explicit]}), catalog, ["bug-fix"])["roles"]["bug-fix"]["seats"]
        self.assertEqual(capped, [codex_max])
        verifiers = roles.resolve(config("unlimited"), catalog, ["verifiers"])["roles"]["verifiers"]["seats"]
        self.assertEqual(verifiers[0], codex_max)
        self.assertNotIn("ultra", json.dumps(verifiers))
        full = roles.resolve(config("unlimited"), CATALOG, ["verifiers"])["roles"]["verifiers"]["seats"]
        self.assertEqual(full[1]["options"]["reasoningEffort"], "max")

    def test_show_writes_ultra_under_every_budget_when_it_is_the_only_level(self):
        only_ultra = {
            "inheritedProviderInstanceId": "codex",
            "inheritedModel": "gpt-6.1-sol",
            "providers": [{
                "providerInstanceId": "codex", "canRunChildTask": True, "constraints": [],
                "models": [{"id": "gpt-6.1-sol", "options": [
                    {"id": "reasoningEffort", "type": "select", "options": [{"id": "ultra"}]},
                ]}],
            }],
        }
        ultra = {"providerInstanceId": "codex", "model": "gpt-6.1-sol", "options": {"reasoningEffort": "ultra"}}
        codex_max = {"providerInstanceId": "codex", "model": "gpt-6.1-sol", "options": {"reasoningEffort": "max"}}

        def show(budget, catalog, seat=None):
            with tempfile.TemporaryDirectory() as directory:
                roles_file = Path(directory) / "pstack-t3" / "roles.json"
                roles_file.parent.mkdir()
                roles_file.write_text(json.dumps({"version": 1, "budget": budget, "roles": {"bug-fix": [seat]} if seat else {}}))
                completed = subprocess.run(
                    [sys.executable, str(ROOT / "t3/scripts/roles.py"), "show", "--cwd", directory,
                     "--catalog", "-", "--parent", "codex/gpt-6.1-sol", "--role", "bug-fix"],
                    input=json.dumps(catalog), env={**os.environ, "XDG_CONFIG_HOME": directory},
                    capture_output=True, text=True, check=True)
            return json.loads(completed.stdout)["roles"]["bug-fix"]["seats"]

        for budget in ("default", "small", "medium", "large", "unlimited"):
            self.assertEqual(show(budget, only_ultra), [ultra], budget)
            self.assertEqual(show(budget, only_ultra, ultra), [ultra], budget)
        self.assertEqual(show("default", CATALOG, ultra), [ultra])
        self.assertEqual(show("unlimited", CATALOG, ultra), [codex_max])

    def test_catalog_stdin_matches_the_file_error_and_accepts_json(self):
        script = [sys.executable, str(ROOT / "t3/scripts/roles.py"), "show", "--role", "bug-fix", "--parent", "claudeAgent/claude-opus-5-5"]
        catalog_text = (ROOT / "tests/fixtures/catalog.json").read_text()

        def detail(stderr):
            line = stderr.strip().splitlines()[-1]
            self.assertTrue(line.startswith("error: "), stderr)
            self.assertIn("invalid JSON: ", line)
            return line.split("invalid JSON: ", 1)[1]

        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "XDG_CONFIG_HOME": directory}
            base = [*script, "--cwd", directory]

            def run(catalog_arg, stdin=""):
                return subprocess.run([*base, "--catalog", catalog_arg], input=stdin, capture_output=True, text=True, env=env)

            valid_stdin = run("-", catalog_text)
            self.assertEqual(valid_stdin.returncode, 0, valid_stdin.stderr)
            valid_file = run(str(ROOT / "tests/fixtures/catalog.json"))
            self.assertEqual(valid_file.returncode, 0, valid_file.stderr)
            self.assertEqual(valid_stdin.stdout, valid_file.stdout)
            self.assertEqual(json.loads(valid_stdin.stdout)["roles"]["bug-fix"]["seats"], [GROK_SEAT])

            bad = Path(directory) / "bad.json"
            empty = Path(directory) / "empty.json"
            bad.write_text("{not json")
            empty.write_text("")
            for stdin_text, file_path in (("", empty), ("{not json", bad)):
                from_stdin = run("-", stdin_text)
                from_file = run(str(file_path))
                self.assertEqual(from_stdin.returncode, 2, from_stdin.stderr)
                self.assertEqual(from_file.returncode, 2, from_file.stderr)
                self.assertNotIn("Traceback", from_stdin.stderr)
                self.assertEqual(detail(from_stdin.stderr), detail(from_file.stderr))

    def test_budget_understands_extra_high_and_keeps_none(self):
        model = {"id": "m", "options": [{"id": "reasoning_effort", "type": "select", "options": [{"id": "none"}, {"id": "low"}, {"id": "high"}, {"id": "extra-high"}]}]}
        self.assertEqual(roles.apply_budget({"model": "m"}, model, "unlimited")["options"], {"reasoning_effort": "extra-high"})
        self.assertEqual(roles.apply_budget({"model": "m", "options": {"reasoning_effort": "none"}}, model, "small")["options"], {"reasoning_effort": "none"})
        self.assertEqual(roles.apply_budget({"model": "m", "options": {"reasoning_effort": "extra-high"}}, model, "small")["options"], {"reasoning_effort": "low"})

    def test_snapshot_parent_comes_from_the_caller_not_the_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            snapshot = base / "pstack-t3" / "catalog.json"
            snapshot.parent.mkdir()
            snapshot.write_text(json.dumps(CATALOG))
            env = {**os.environ, "XDG_CONFIG_HOME": str(base)}
            run = lambda *extra: json.loads(subprocess.run([sys.executable, str(ROOT / "t3/scripts/roles.py"), "show", "--cwd", directory, "--role", "verifiers", *extra],
                                                           env=env, capture_output=True, text=True, check=True).stdout)
            seats = run("--parent", "codex/gpt-6.1-sol")["roles"]["verifiers"]["seats"]
            self.assertEqual(seats[0], "inherit")
            self.assertIn({"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5"}, seats)
            self.assertNotIn({"providerInstanceId": "codex", "model": "gpt-6.1-sol"}, seats)

    def test_panel_with_one_runnable_provider_is_three_inherit_seats(self):
        catalog = {**CATALOG, "providers": [p for p in CATALOG["providers"] if p["providerInstanceId"] == "claudeAgent"]}
        seats = roles.resolve(config(), catalog, ["verifiers"])["roles"]["verifiers"]["seats"]
        self.assertEqual(seats, ["inherit", "inherit", "inherit"])

    def test_arena_runners_with_one_runnable_provider_keeps_two_fallback_seats(self):
        catalog = {**CATALOG, "providers": [p for p in CATALOG["providers"] if p["providerInstanceId"] == "claudeAgent"]}
        entry = roles.resolve(config(), catalog, ["arena runners"])["roles"]["arena runners"]
        self.assertEqual(entry["seats"], [OPUS_SEAT, OPUS_SEAT])
        self.assertNotIn("fastMode", entry["seats"][1].get("options", {}))
        self.assertEqual(entry["notes"], [
            "arena runners seat 2: wanted grok-4.7, using claudeAgent/claude-opus-5-5 (missing family)",
            "arena runners: seats 1 and 2 both use claudeAgent/claude-opus-5-5, so the panel lost a distinct model",
        ])

    def test_without_catalog_panels_are_reported_for_the_agent_to_expand(self):
        note = (
            "expand from orchestrator_capabilities: this thread inherits, "
            "then one seat per runnable provider whose first model is a new model family"
        )
        unknown = roles.resolve(config(), None, ["verifiers"])["roles"]["verifiers"]
        self.assertEqual(unknown["seats"], "default-panel")
        self.assertEqual(unknown["note"], note)
        named = roles.resolve(config(), None, ["verifiers"], roles.Parent("grok", "grok-4.7"))["roles"]["verifiers"]
        self.assertEqual(named["seats"], "default-panel")
        self.assertEqual(named["note"], note)

    def test_preferred_roles_without_a_catalog_ask_for_one(self):
        entry = roles.resolve(config(), None, ["bug-fix"])["roles"]["bug-fix"]
        self.assertEqual(entry["seats"], "catalog-required")
        self.assertEqual(entry["note"], "call orchestrator_capabilities and rerun roles.py show --catalog")
        panel = roles.resolve(config(), None, ["arena runners"])["roles"]["arena runners"]
        self.assertEqual(panel["seats"], "catalog-required")
        skill = roles.resolve(config(), None, ["skill tests"])["roles"]["skill tests"]
        self.assertEqual(skill["seats"], "catalog-required")
        inherited = roles.resolve(config(**{"bug-fix": ["inherit"]}), None, ["bug-fix"])["roles"]["bug-fix"]
        self.assertEqual(inherited["seats"], ["inherit"])

    def test_unrunnable_provider_falls_back_to_inherit_with_a_note(self):
        entry = roles.resolve(config(**{"swarm workers": [{"providerInstanceId": "cursor", "model": "default"}]}), CATALOG, ["swarm workers"])["roles"]["swarm workers"]
        self.assertEqual(entry["seats"], ["inherit"])
        self.assertIn("not authenticated", entry["notes"][0])

    def test_missing_model_falls_back_to_first_model_of_the_provider(self):
        entry = roles.resolve(config(**{"bug-fix": [{"providerInstanceId": "codex", "model": "gpt-9"}]}), CATALOG, ["bug-fix"])["roles"]["bug-fix"]
        self.assertEqual(entry["seats"], [{"providerInstanceId": "codex", "model": "gpt-6.1-sol"}])
        self.assertIn("gpt-9", entry["notes"][0])

    def test_budget_caps_explicit_effort_and_skips_special_values(self):
        seat = {"providerInstanceId": "codex", "model": "gpt-6.1-sol", "options": {"reasoningEffort": "ultra"}}
        resolved = roles.resolve(config("large", **{"bug-fix": [seat]}), CATALOG, ["bug-fix"])["roles"]["bug-fix"]["seats"][0]
        self.assertEqual(resolved["options"], {"reasoningEffort": "xhigh"})
        claude = {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5"}
        resolved = roles.resolve(config("unlimited", **{"bug-fix": [claude]}), CATALOG, ["bug-fix"])["roles"]["bug-fix"]["seats"][0]
        self.assertEqual(resolved["options"], {"effort": "max"})

    def test_budget_keeps_a_lower_explicit_choice(self):
        seat = {"providerInstanceId": "grok", "model": "grok-4.7", "options": {"reasoningEffort": "low"}}
        resolved = roles.resolve(config("large", **{"bug-fix": [seat]}), CATALOG, ["bug-fix"])["roles"]["bug-fix"]["seats"][0]
        self.assertEqual(resolved["options"], {"reasoningEffort": "low"})

    def test_budget_leaves_models_without_effort_alone(self):
        seat = {"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5", "options": {"fastMode": True}}
        resolved = roles.resolve(config("small", **{"bug-fix": [seat]}), CATALOG, ["bug-fix"])["roles"]["bug-fix"]["seats"][0]
        self.assertEqual(resolved["options"], {"fastMode": True, "effort": "medium"})

    def test_model_fallback_keeps_options_the_fallback_model_supports(self):
        seat = {"providerInstanceId": "codex", "model": "gone", "options": {"reasoningEffort": "low", "serviceTier": "priority"}}
        entry = roles.resolve(config("large", **{"bug-fix": [seat]}), CATALOG, ["bug-fix"])["roles"]["bug-fix"]
        self.assertEqual(entry["seats"][0]["options"], {"reasoningEffort": "low", "serviceTier": "priority"})

    def test_panel_when_parent_provider_cannot_run_children(self):
        catalog = {**CATALOG, "inheritedProviderInstanceId": "cursor", "inheritedModel": "grok-4.7",
                   "providers": [p for p in CATALOG["providers"] if p["providerInstanceId"] in ("cursor", "grok")]}
        seats = roles.resolve(config(), catalog, ["verifiers"])["roles"]["verifiers"]["seats"]
        self.assertEqual(seats, [{"providerInstanceId": "grok", "model": "grok-4.7"}] * 3)

    def test_parse_seat(self):
        self.assertEqual(roles.parse_seat("inherit"), "inherit")
        self.assertEqual(roles.parse_seat("codex/gpt-6.1-sol?reasoningEffort=high&fast=true"),
                         {"providerInstanceId": "codex", "model": "gpt-6.1-sol", "options": {"reasoningEffort": "high", "fast": True}})
        with self.assertRaises(roles.RolesError):
            roles.parse_seat("gpt-6.1-sol")

    def test_single_role_rejects_two_seats(self):
        with self.assertRaises(roles.RolesError):
            roles.check_shape({"roles": {"bug-fix": ["inherit", "inherit"]}}, "test")

    def test_project_roles_override_user_roles_per_role(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "user.json").write_text(json.dumps({"budget": "small", "roles": {"bug-fix": ["inherit"], "hillclimb": ["inherit"]}}))
            (base / "project.json").write_text(json.dumps({"roles": {"bug-fix": [{"providerInstanceId": "grok", "model": "grok-4.7"}]}}))
            merged = roles.merged_config(base, base / "user.json", base / "project.json")
        self.assertEqual(merged["budget"], "small")
        self.assertEqual(merged["roles"]["bug-fix"][0]["providerInstanceId"], "grok")
        self.assertEqual(merged["roles"]["hillclimb"], ["inherit"])

    def test_project_write_without_budget_keeps_the_user_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / ".git").mkdir()
            user = base / "user.json"
            user.write_text(json.dumps({"budget": "large", "roles": {}}))
            catalog = str(ROOT / "tests/fixtures/catalog.json")
            self.assertEqual(roles.main(["write", "--project", "--cwd", directory, "--catalog", catalog, "--set", "bug-fix=inherit"]), 0)
            project = base / ".pstack/t3-roles.json"
            self.assertNotIn("budget", json.loads(project.read_text()))
            self.assertEqual(roles.merged_config(base, user, project)["budget"], "large")

    def test_write_refuses_seats_outside_the_catalog_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "roles.json"
            catalog = str(ROOT / "tests/fixtures/catalog.json")
            bad = roles.main(["write", "--config", str(target), "--catalog", catalog, "--set", "bug-fix=cursor/default"])
            self.assertEqual(bad, 2)
            self.assertFalse(target.exists())
            args = ["write", "--config", str(target), "--catalog", catalog, "--budget", "large", "--set", "interrogate reviewers=inherit;codex/gpt-6.1-sol"]
            self.assertEqual(roles.main(args), 0)
            first = target.read_text()
            self.assertEqual(roles.main(args), 0)
            self.assertEqual(target.read_text(), first)
            self.assertEqual(json.loads(first)["roles"]["interrogate reviewers"][1]["model"], "gpt-6.1-sol")

    def test_missing_grok_model_names_the_replacement(self):
        grok = {
            "providerInstanceId": "grok", "canRunChildTask": True, "constraints": [],
            "models": [{"id": "grok-4.5", "options": [{"id": "reasoningEffort", "type": "select", "options": [
                {"id": "xhigh"}, {"id": "high"}, {"id": "medium"}, {"id": "low"}]}]}],
        }
        providers = [grok if provider["providerInstanceId"] == "grok" else provider for provider in CATALOG["providers"]]
        entry = roles.resolve(config(), {**CATALOG, "providers": providers}, ["swarm workers"])["roles"]["swarm workers"]
        self.assertEqual(entry["seats"], [{"providerInstanceId": "grok", "model": "grok-4.5", "options": {"reasoningEffort": "xhigh"}}])
        self.assertEqual(entry["notes"], ["swarm workers seat 1: wanted grok-4.7, using grok/grok-4.5 (missing model)"])

    def test_codex_only_catalog_substitutes_both_panel_seats(self):
        codex = next(provider for provider in CATALOG["providers"] if provider["providerInstanceId"] == "codex")
        catalog = {"inheritedProviderInstanceId": "codex", "inheritedModel": "gpt-6.1-sol", "providers": [codex]}
        entry = roles.resolve(config(), catalog, ["interrogate reviewers"])["roles"]["interrogate reviewers"]
        seat = {"providerInstanceId": "codex", "model": "gpt-6.1-sol", "options": {"reasoningEffort": "xhigh"}}
        self.assertEqual(entry["seats"], [seat, seat])
        self.assertEqual(entry["notes"], [
            "interrogate reviewers seat 1: wanted claude-opus-5-5, using codex/gpt-6.1-sol (missing family)",
            "interrogate reviewers seat 2: wanted grok-4.7, using codex/gpt-6.1-sol (missing family)",
            "interrogate reviewers: seats 1 and 2 both use codex/gpt-6.1-sol, so the panel lost a distinct model",
        ])

    def test_no_runnable_model_raises(self):
        catalog = {"providers": [{"providerInstanceId": "cursor", "canRunChildTask": False,
                                  "constraints": ["Provider is not authenticated."], "models": [{"id": "default", "options": []}]}]}
        for name in ("bug-fix", "verifiers"):
            with self.assertRaises(roles.RolesError) as caught:
                roles.resolve(config(), catalog, [name])
            self.assertIn("no provider in the catalog can run child tasks", str(caught.exception))

    def test_custom_runnable_provider_serves_a_preferred_model(self):
        grok = next(provider for provider in CATALOG["providers"] if provider["providerInstanceId"] == "grok")
        blocked = {**grok, "canRunChildTask": False, "constraints": ["Provider is not authenticated."]}
        custom = {
            "providerInstanceId": "acme", "canRunChildTask": True, "constraints": [],
            "models": [{"id": "grok-4.7", "options": [
                {"id": "reasoningEffort", "type": "select", "options": [{"id": "xhigh"}, {"id": "high"}]},
                {"id": "fastMode", "type": "boolean"},
            ]}],
        }
        providers = [blocked if provider["providerInstanceId"] == "grok" else provider for provider in CATALOG["providers"]]
        providers.append(custom)
        entry = roles.resolve(config(), {**CATALOG, "providers": providers}, ["swarm workers"])["roles"]["swarm workers"]
        self.assertEqual(entry["seats"], [{"providerInstanceId": "acme", "model": "grok-4.7", "options": {"reasoningEffort": "xhigh", "fastMode": False}}])
        self.assertNotIn("notes", entry)

    def test_unauthenticated_only_copy_falls_back_to_the_parent(self):
        grok = next(provider for provider in CATALOG["providers"] if provider["providerInstanceId"] == "grok")
        blocked = {**grok, "canRunChildTask": False, "constraints": ["Provider is not authenticated."]}
        providers = [blocked if provider["providerInstanceId"] == "grok" else provider for provider in CATALOG["providers"]]
        entry = roles.resolve(config(), {**CATALOG, "providers": providers}, ["swarm workers"])["roles"]["swarm workers"]
        self.assertEqual(entry["seats"], [OPUS_SEAT])
        self.assertNotIn("fastMode", entry["seats"][0]["options"])
        self.assertEqual(entry["notes"], ["swarm workers seat 1: wanted grok-4.7, using claudeAgent/claude-opus-5-5 (missing family)"])

    def test_claude_and_codex_catalog_without_grok_does_not_set_fast_mode(self):
        providers = [provider for provider in CATALOG["providers"] if provider["providerInstanceId"] in ("claudeAgent", "codex")]
        catalog = {**CATALOG, "providers": providers}
        entry = roles.resolve(config(), catalog, ["bug-fix"])["roles"]["bug-fix"]
        self.assertEqual(entry["seats"], [OPUS_SEAT])
        self.assertNotIn("fastMode", entry["seats"][0]["options"])
        self.assertIn("missing family", entry["notes"][0])
        panel = roles.resolve(config(), catalog, ["interrogate reviewers"])["roles"]["interrogate reviewers"]
        self.assertEqual(panel["seats"][1], OPUS_SEAT)
        self.assertNotIn("fastMode", panel["seats"][1]["options"])

    def test_exact_model_prefers_the_provider_whose_first_model_is_in_the_family(self):
        wrapper = {
            "providerInstanceId": "wrapper", "canRunChildTask": True, "constraints": [],
            "models": [
                {"id": "gpt-9", "options": []},
                {"id": "grok-4.7", "options": [{"id": "reasoningEffort", "type": "select", "options": [{"id": "xhigh"}]}]},
            ],
        }
        grok = next(provider for provider in CATALOG["providers"] if provider["providerInstanceId"] == "grok")
        providers = [wrapper] + [provider for provider in CATALOG["providers"] if provider["providerInstanceId"] != "grok"] + [grok]
        entry = roles.resolve(config(), {**CATALOG, "providers": providers}, ["swarm workers"])["roles"]["swarm workers"]
        self.assertEqual(entry["seats"], [{"providerInstanceId": "grok", "model": "grok-4.7", "options": {"reasoningEffort": "xhigh"}}])
        self.assertNotIn("notes", entry)

    def test_exact_model_keeps_catalog_order_when_no_first_model_is_in_the_family(self):
        def carrier(provider_id, first_model):
            return {
                "providerInstanceId": provider_id, "canRunChildTask": True, "constraints": [],
                "models": [
                    {"id": first_model, "options": []},
                    {"id": "grok-4.7", "options": [{"id": "reasoningEffort", "type": "select", "options": [{"id": "xhigh"}]}]},
                ],
            }
        providers = [carrier("first", "gpt-9"), carrier("second", "claude-haiku-9")]
        providers.extend(provider for provider in CATALOG["providers"] if provider["providerInstanceId"] != "grok")
        entry = roles.resolve(config(), {**CATALOG, "providers": providers}, ["swarm workers"])["roles"]["swarm workers"]
        self.assertEqual(entry["seats"], [{"providerInstanceId": "first", "model": "grok-4.7", "options": {"reasoningEffort": "xhigh"}}])
        self.assertNotIn("notes", entry)

    def test_preferred_seat_notes_a_lower_declared_effort(self):
        grok = {
            "providerInstanceId": "grok", "canRunChildTask": True, "constraints": [],
            "models": [{"id": "grok-4.7", "options": [{"id": "reasoningEffort", "type": "select", "options": [
                {"id": "high"}, {"id": "medium"}, {"id": "low"}]}]}],
        }
        providers = [grok if provider["providerInstanceId"] == "grok" else provider for provider in CATALOG["providers"]]
        for budget in ("default", "unlimited"):
            with self.subTest(budget=budget):
                entry = roles.resolve(config(budget), {**CATALOG, "providers": providers}, ["bug-fix"])["roles"]["bug-fix"]
                self.assertEqual(entry["seats"], [{"providerInstanceId": "grok", "model": "grok-4.7", "options": {"reasoningEffort": "high"}}])
                self.assertEqual(entry["notes"], ["bug-fix seat 1: wanted xhigh, using high"])

    def test_preferred_seat_adds_no_effort_option_when_the_model_declares_none(self):
        grok = {"providerInstanceId": "grok", "canRunChildTask": True, "constraints": [], "models": [{"id": "grok-4.7", "options": []}]}
        providers = [grok if provider["providerInstanceId"] == "grok" else provider for provider in CATALOG["providers"]]
        entry = roles.resolve(config(), {**CATALOG, "providers": providers}, ["bug-fix"])["roles"]["bug-fix"]
        self.assertEqual(entry["seats"], [{"providerInstanceId": "grok", "model": "grok-4.7"}])
        self.assertNotIn("notes", entry)

    def test_extra_high_spelling_satisfies_the_builtin_ceiling(self):
        grok = {
            "providerInstanceId": "grok", "canRunChildTask": True, "constraints": [],
            "models": [{"id": "grok-4.7", "options": [{"id": "reasoningEffort", "type": "select", "options": [
                {"id": "high"}, {"id": "extra-high"}]}]}],
        }
        providers = [grok if provider["providerInstanceId"] == "grok" else provider for provider in CATALOG["providers"]]
        entry = roles.resolve(config(), {**CATALOG, "providers": providers}, ["bug-fix"])["roles"]["bug-fix"]
        self.assertEqual(entry["seats"], [{"providerInstanceId": "grok", "model": "grok-4.7", "options": {"reasoningEffort": "extra-high"}}])
        self.assertNotIn("notes", entry)

    def test_explicit_codex_seat_wins_over_the_builtin(self):
        seat = {"providerInstanceId": "codex", "model": "gpt-6.1-sol", "options": {"reasoningEffort": "high"}}
        entry = roles.resolve(config("large", **{"bug-fix": [seat]}), CATALOG, ["bug-fix"])["roles"]["bug-fix"]
        self.assertEqual(entry["seats"], [seat])
        self.assertEqual(entry["source"], "test")
        self.assertNotIn("notes", entry)

    def test_configured_panel_keeps_its_seat_count(self):
        seats = ["inherit", {"providerInstanceId": "codex", "model": "gpt-6.1-sol"}, {"providerInstanceId": "grok", "model": "grok-4.7"}]
        entry = roles.resolve(config(**{"interrogate reviewers": seats}), CATALOG, ["interrogate reviewers"])["roles"]["interrogate reviewers"]
        self.assertEqual(entry["seats"][0], "inherit")
        self.assertEqual(len(entry["seats"]), 3)
        self.assertEqual(entry["source"], "test")

    def test_resolve_does_not_mutate_inputs_and_repeats(self):
        catalog = json.loads(json.dumps(CATALOG))
        before_catalog = json.dumps(catalog)
        before_roles = json.dumps(roles.ROLES)
        cfg = config()
        before_cfg = json.dumps(cfg)
        first = roles.resolve(cfg, catalog)
        second = roles.resolve(cfg, catalog)
        self.assertEqual(first, second)
        self.assertEqual(json.dumps(catalog), before_catalog)
        self.assertEqual(json.dumps(roles.ROLES), before_roles)
        self.assertEqual(json.dumps(cfg), before_cfg)
        self.assertEqual([seat.model_id for seat in (roles.OPUS, roles.GROK)], ["claude-opus-5-5", "grok-4.7"])

    def test_runtime_describes_the_builtin_policy(self):
        text = (ROOT / "t3/runtime.md").read_text()
        self.assertIn("catalog-required", text)
        self.assertIn("Do not reconstruct role defaults", text)
        self.assertNotIn("Expand it yourself", text)
        self.assertIn("`gpt-6.1-sol` is `gpt`", text)
        self.assertNotIn('"model": "gpt-6.1-sol"', text)
        defaults = text.split("### Built-in defaults", 1)[1].split("### Budget", 1)[0]
        self.assertIn('`verifiers` is three `"inherit"` seats', defaults)
        self.assertIn("roles.py show` owns this mapping", defaults)

    def test_setup_stops_before_writing_when_watch_is_absent(self):
        text = (ROOT / "t3/setup.md").read_text()
        self.assertIn(
            'Say "Setup cannot finish. T3 Code 0.0.46-nightly.20261005.2702 or later is required because this host does not expose watch_pull_request."',
            text,
        )
        self.assertIn("stop setup before writing roles or a saved catalog", text)
        self.assertIn("A deferred `watch_pull_request` counts as present", text)
        self.assertIn("dummy PR", text)

    def test_skill_tests_returns_haiku_when_both_haiku_versions_exist(self):
        thinking = [{"id": "thinking", "type": "boolean"}]
        effort = [{"id": "effort", "type": "select", "options": [{"id": "medium", "isDefault": True}, {"id": "high"}]}]
        haiku_4 = {"id": "claude-haiku-4-5", "options": thinking}
        haiku_5 = {"id": "claude-haiku-5-5", "options": effort}
        catalog = {
            "inheritedProviderInstanceId": "grok",
            "inheritedModel": "grok-4.7",
            "providers": [{
                "providerInstanceId": "claudeAgent", "canRunChildTask": True, "constraints": [],
                "models": [haiku_4, haiku_5],
            }],
        }
        entry = roles.resolve(config(), catalog, ["skill tests"])["roles"]["skill tests"]
        self.assertEqual(entry["seats"], [{"providerInstanceId": "claudeAgent", "model": "claude-haiku-5-5", "options": {"effort": "high"}}])

    def test_configured_haiku_seat_loads_on_any_role(self):
        seat = {"providerInstanceId": "claudeAgent", "model": "anthropic/claude-haiku-5-5"}
        roles.check_shape({"roles": {"swarm workers": [seat]}}, "roles.json")

    def test_missing_model_skips_excluded_haiku_45(self):
        catalog = {
            "inheritedProviderInstanceId": "grok",
            "inheritedModel": "grok-4.7",
            "providers": [{
                "providerInstanceId": "cursor", "canRunChildTask": True, "constraints": [],
                "models": [
                    {"id": "claude-haiku-5-5", "options": [{"id": "effort", "type": "select", "options": [{"id": "high"}]}]},
                    {"id": "claude-haiku-4-5", "options": []},
                ],
            }],
        }
        entry = roles.resolve(
            config(**{"bug-fix": [{"providerInstanceId": "cursor", "model": "claude-gone"}]}),
            catalog,
            ["bug-fix"],
        )["roles"]["bug-fix"]
        self.assertEqual(entry["seats"], [{"providerInstanceId": "cursor", "model": "claude-haiku-5-5"}])

    def test_haiku_parent_inherit_resolves_for_how_explorer(self):
        catalog = {
            "inheritedProviderInstanceId": "claudeAgent",
            "inheritedModel": "claude-haiku-5-5",
            "providers": [{
                "providerInstanceId": "claudeAgent", "canRunChildTask": True, "constraints": [],
                "models": [{"id": "claude-haiku-5-5", "options": [
                    {"id": "effort", "type": "select", "options": [{"id": "medium", "isDefault": True}, {"id": "high"}]},
                ]}],
            }],
        }
        entry = roles.resolve(config(**{"how explorer": ["inherit"]}), catalog, ["how explorer"])["roles"]["how explorer"]
        self.assertEqual(entry["seats"], ["inherit"])
        self.assertEqual(entry["haikuBrief"], list(roles.HAIKU_BRIEF))

    def test_direct_resolve_keeps_exclusion_notes_when_cursor_is_ignored(self):
        # check_shape rejects two skill tests seats at the CLI, so this calls resolve directly.
        cfg = {
            "budget": "default",
            "roles": {"skill tests": [
                {"providerInstanceId": "grok", "model": "grok-4.7-build-fast"},
                {"providerInstanceId": "cursor", "model": "claude-haiku-5-5"},
            ]},
            "sources": {"skill tests": "fixture-config"},
        }
        entry = roles.resolve(
            cfg, CATALOG, ["skill tests"],
            providers={"claudeAgent", "grok"}, launches_seats=True,
        )["roles"]["skill tests"]
        self.assertEqual(entry["seats"], [{
            "providerInstanceId": "claudeAgent",
            "model": "claude-haiku-5-5",
            "options": {"effort": "high"},
        }])
        self.assertEqual(entry["notes"], [
            "skipped configured seat grok/grok-4.7-build-fast: "
            "grok-4.7-build-fast is a fast Grok variant, and "
            "pstack never runs a fast Grok model or Claude Haiku 4.5 as a seat or a worker",
        ])
        self.assertEqual(entry["source"], "fixture-config")
        self.assertEqual(entry["haikuBrief"], list(roles.HAIKU_BRIEF))


class InstallTest(unittest.TestCase):
    def run_install(self, home, *args):
        env = {**os.environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config")}
        env.pop("CLAUDE_CONFIG_DIR", None)
        return subprocess.run([sys.executable, str(ROOT / "scripts/install.py"), *args], env=env, capture_output=True, text=True)

    def setUp(self):
        if not (ROOT / "skills/pstack-runtime/SKILL.md").exists():
            subprocess.run([sys.executable, str(ROOT / "scripts/build.py")], check=True)

    def test_install_refuses_conflicts_then_replace_and_uninstall_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            existing = home / ".claude/skills/swarm"
            existing.mkdir(parents=True)
            (existing / "SKILL.md").write_text("mine")
            refused = self.run_install(home)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("swarm", refused.stderr)
            self.assertFalse((home / ".grok/skills/poteto-mode").exists())
            replaced = self.run_install(home, "--replace")
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            for harness in (".claude", ".agents", ".grok", ".cursor"):
                self.assertTrue((home / harness / "skills/poteto-mode/SKILL.md").exists(), harness)
            self.assertEqual(self.run_install(home, "doctor").returncode, 0)
            again = self.run_install(home)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("already installed", again.stdout)
            self.assertEqual(self.run_install(home, "uninstall").returncode, 0)
            self.assertEqual((existing / "SKILL.md").read_text(), "mine")
            self.assertFalse((home / ".grok/skills/poteto-mode").exists())

    def test_uninstall_dry_run_changes_nothing_and_harness_filter_is_respected(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertEqual(self.run_install(home, "--harness", "codex,grok").returncode, 0)
            dry = self.run_install(home, "uninstall", "--dry-run")
            self.assertIn("would remove", dry.stdout)
            self.assertTrue((home / ".agents/skills/swarm").is_symlink())
            self.assertEqual(self.run_install(home, "uninstall", "--harness", "codex").returncode, 0)
            self.assertFalse((home / ".agents/skills/swarm").exists())
            self.assertTrue((home / ".grok/skills/swarm").is_symlink())
            self.assertEqual(self.run_install(home, "uninstall").returncode, 0)
            self.assertFalse((home / ".grok/skills/swarm").exists())

    def test_blocked_restore_keeps_its_backup_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            mine = home / ".grok/skills/swarm"
            mine.mkdir(parents=True)
            (mine / "SKILL.md").write_text("mine")
            self.assertEqual(self.run_install(home, "--harness", "grok", "--replace").returncode, 0)
            (mine).unlink()
            mine.mkdir()
            (mine / "SKILL.md").write_text("squatter")
            self.run_install(home, "uninstall")
            self.assertEqual((mine / "SKILL.md").read_text(), "squatter")
            shutil.rmtree(mine)
            self.run_install(home, "uninstall")
            self.assertEqual((mine / "SKILL.md").read_text(), "mine")

    def test_two_replacements_in_one_second_keep_both_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            target = home / ".grok/skills/swarm"
            target.parent.mkdir(parents=True)
            for text in ("first", "second"):
                if target.is_symlink():
                    target.unlink()
                target.write_text(text)
                self.assertEqual(self.run_install(home, "--harness", "grok", "--replace").returncode, 0)
            backups = sorted(p.read_text() for p in (home / ".config/pstack-t3/backups").rglob("swarm"))
            self.assertEqual(backups, ["first", "second"])

    def test_replace_never_moves_the_checkout_when_a_skills_dir_points_into_it(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".grok").mkdir()
            (home / ".grok/skills").symlink_to(ROOT / "skills")
            result = self.run_install(home, "--harness", "grok", "--replace")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((ROOT / "skills/swarm/SKILL.md").is_file())
            self.assertFalse((ROOT / "skills/swarm").is_symlink())
            self.assertEqual(self.run_install(home, "uninstall").returncode, 0)
            self.assertTrue((ROOT / "skills/swarm/SKILL.md").is_file())

    def test_shared_directory_uninstalls_only_when_every_sharing_harness_is_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".agents/skills").mkdir(parents=True)
            (home / ".grok").mkdir()
            (home / ".grok/skills").symlink_to(home / ".agents/skills")
            self.assertEqual(self.run_install(home, "--harness", "codex,grok").returncode, 0)
            partial = self.run_install(home, "uninstall", "--harness", "grok")
            self.assertIn("shared with codex", partial.stdout)
            self.assertTrue((home / ".agents/skills/swarm").is_symlink())
            self.assertEqual(self.run_install(home, "uninstall", "--harness", "codex,grok").returncode, 0)
            self.assertFalse((home / ".agents/skills/swarm").exists())

    def test_doctor_fails_when_a_skills_dir_points_inside_one_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".grok").mkdir()
            (home / ".grok/skills").symlink_to(ROOT / "skills/swarm")
            self.assertNotEqual(self.run_install(home, "doctor", "--harness", "grok").returncode, 0)

    def test_doctor_flags_stale_copies_in_directories_a_provider_also_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            self.assertEqual(self.run_install(home, "--harness", "codex").returncode, 0)
            (home / ".codex/skills/swarm").mkdir(parents=True)
            (home / ".codex/skills/swarm/SKILL.md").write_text("old")
            result = self.run_install(home, "doctor", "--harness", "codex")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(".codex/skills also holds other copies", result.stdout)

    def test_shared_real_directory_is_linked_once(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            shared = home / "shared"
            shared.mkdir()
            (home / ".grok").mkdir()
            (home / ".cursor").mkdir()
            (home / ".grok/skills").symlink_to(shared)
            (home / ".cursor/skills").symlink_to(shared)
            result = self.run_install(home, "--harness", "grok,cursor")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((shared / "swarm/SKILL.md").exists())


CODE_DELEGATE_SITES = (
    ("poteto-mode/playbooks/feature.md", "4. Delegate code-writing", "Playbook: playbooks/feature.md"),
    ("poteto-mode/playbooks/refactoring.md", "5. Move in small", "Playbook: playbooks/refactoring.md"),
    ("poteto-mode/playbooks/bug-fix.md", "3. Plan the fix.", "Playbook: playbooks/bug-fix.md"),
    ("poteto-mode/playbooks/perf-issue.md", "3. Plan the fix from the trace.", "Playbook: playbooks/perf-issue.md"),
    ("poteto-mode/playbooks/hillclimb.md", "   - Hand the change", "Playbook: playbooks/hillclimb.md"),
    ("swarm/SKILL.md", "Every brief stands alone.", "Playbook: playbooks/<name>.md"),
    ("arena/SKILL.md", "Spawn all N candidates", "Playbook: playbooks/<name>.md"),
)


class CodeDelegateBriefTest(unittest.TestCase):
    def test_every_code_delegate_step_points_at_the_brief_check(self):
        for path, step, playbook_line in CODE_DELEGATE_SITES:
            lines = (ROOT / "skills" / path).read_text().splitlines()
            matches = [line for line in lines if line.startswith(step)]
            self.assertEqual(len(matches), 1, (path, step))
            for needed in ("pstack-runtime/SKILL.md#delegation)", "poteto-agent persona first", playbook_line, "`roles.py mode --playbook ", "`roles.py check-brief` before `delegate_task`"):
                self.assertIn(needed, matches[0], path)

    def test_routed_skill_exception_excludes_code_writing_children(self):
        text = (ROOT / "skills/poteto-mode/SKILL.md").read_text()
        self.assertIn("It never covers a code-writing child.", text)


MODE_POINTER_SITES = {
    **{f"{name}/SKILL.md": "skill" for name in (
        "poteto-mode", "how", "why", "architect", "arena", "no-comments", "swarm", "interrogate",
        "show-me-your-work", "recall", "automate-me", "maintain-verification-skill", "reflect",
        "pstack-author-skill", "landing",
    )},
    **{f"poteto-mode/playbooks/{stem}.md": "playbook" for stem in (
        "feature", "bug-fix", "refactoring", "perf-issue", "hillclimb", "opening-a-pr",
        "autopilot-full", "autopilot-stack", "multi-phase-plan", "orchestrate", "shipping",
        "visual-parity", "worktree-cleanup",
    )},
}
MODES_UNCHANGED = {
    "pstack-runtime/SKILL.md": "the Modes section's home",
    "brigade/SKILL.md": "brigade's mode lands in its own change",
    "brigade-admin/SKILL.md": "launches only standing threads, the admin and a coordinator the user asks for, which light mode keeps",
    "setup-pstack/SKILL.md": "the smoke test is kept, one per provider",
    "poteto-help/SKILL.md": "names delegate_task to explain the persona and spawns nothing",
    "poteto-mode/playbooks/autonomous-run.md": "the watcher is kept",
    "poteto-mode/playbooks/eval.md": "keeps arena and its judge, because comparing candidates is its purpose",
}
SPAWNS = re.compile(r"delegate_task|t3_thread_launch|create_threads")
RUNTIME_LINK = re.compile(r"pstack-runtime/SKILL\.md#([^)\s]+)\)")


def pointer_sentence(kind):
    rel = "../pstack-runtime/SKILL.md" if kind == "skill" else "../../pstack-runtime/SKILL.md"
    return (
        f"[The runtime's Modes section]({rel}#modes) sets the mode lines of every brief "
        f"this {kind} writes and how its spawns run in light mode."
    )


def unfenced_lines(text):
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if not fenced:
            yield line


def heading_slug(heading):
    kept = "".join(char for char in heading.lower() if char.isalnum() or char in " -")
    return kept.replace(" ", "-")


GATE_CONTRACT = """\
Gate review contract. These rules override the persona above and the tasks below where they differ.
Do not edit files, commit, or push. Do not post on the PR. Return your report to the parent.
Launch no child task, thread, or subagent. Do not run the how, why, architect, or interrogate skill. Do not launch show-me-your-work's trail reviewer.
Read the whole diff and the nearby code yourself. You may run git log -L and git blame. Run the named verification commands yourself.
When a claim or finding needs investigation beyond those reads, return send-back. Name the file, the line, the claim, and the question the fix must answer.
Report each comment the persona would delete as a send-back finding with its path and line. Make no edit.
End with pass, send-back, or blocked, the full head SHA, the author, and the verifier.
"""

SEAT_RULE = """\
Seat rule. Copy the Mode value above into --brief-mode on every roles.py mode and roles.py show call you make, and pass no other mode flag. Never pass --session-mode. Mode source names where your launcher's decision came from. It does not make this thread a session.
"""


def gate_contract(runtime):
    start = runtime.index("2. **Brief.**")
    window = runtime[start:].split("\n3. **Verdict.**", 1)[0]
    lines = window.splitlines()
    open_at = next(i for i, line in enumerate(lines) if line.strip() == "```text")
    close_at = next(i for i, line in enumerate(lines) if i > open_at and line.strip() == "```")
    body = "\n".join(lines[open_at + 1:close_at]) + "\n"
    return textwrap.dedent(body)


def seat_rule(runtime):
    start = runtime.index("is not a code delegate")
    window = runtime[start:].split("\n- A read-only leaf", 1)[0]
    lines = window.splitlines()
    open_at = next(i for i, line in enumerate(lines) if line.strip() == "```text")
    close_at = next(i for i, line in enumerate(lines) if i > open_at and line.strip() == "```")
    body = "\n".join(lines[open_at + 1:close_at]) + "\n"
    return textwrap.dedent(body)


def brief_paragraph(runtime):
    start = runtime.index("2. **Brief.**")
    window = runtime[start:].split("\n3. **Verdict.**", 1)[0]
    prose = []
    for line in window.splitlines():
        if line.strip().startswith("```"):
            break
        if prose and not line.strip():
            break
        if line.strip():
            prose.append(line.strip())
    return " ".join(prose)


def light_behavior_rows(runtime):
    section = runtime.split("### Light behavior", 1)[1].split("\n### ", 1)[0]
    rows = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            if rows:
                break
            continue
        if not stripped.replace("|", "").replace(":", "").replace("-", "").strip():
            continue
        if stripped.strip("|").split("|", 1)[0].strip() == "Spawn":
            continue
        rows.append(stripped)
    return rows


def light_row(runtime, spawn):
    matches = [row for row in light_behavior_rows(runtime) if row.split("|", 2)[1].strip() == spawn]
    if len(matches) != 1:
        raise AssertionError(f"{spawn}: expected 1 light row, found {len(matches)}")
    return matches[0]


class ModesTest(unittest.TestCase):
    def setUp(self):
        self.runtime = (ROOT / "skills/pstack-runtime/SKILL.md").read_text()

    def test_every_pointer_site_holds_the_pointer_once_outside_a_fence(self):
        for path, kind in MODE_POINTER_SITES.items():
            text = (ROOT / "skills" / path).read_text()
            sentence = pointer_sentence(kind)
            with self.subTest(path=path):
                self.assertEqual(text.count(sentence), 1)
                self.assertIn(sentence, list(unfenced_lines(text)))

    def test_every_spawning_file_points_at_modes_or_says_why_not(self):
        skills = ROOT / "skills"
        spawning = sorted(
            str(path.relative_to(skills))
            for path in [*skills.glob("*/SKILL.md"), *skills.glob("poteto-mode/playbooks/*.md")]
            if SPAWNS.search(path.read_text())
        )
        self.assertEqual([path for path in spawning if path not in MODE_POINTER_SITES and path not in MODES_UNCHANGED], [])
        self.assertEqual([path for path in MODES_UNCHANGED if not (skills / path).is_file()], [])
        self.assertEqual(set(MODE_POINTER_SITES) & set(MODES_UNCHANGED), set())

    def test_every_runtime_link_names_a_runtime_heading(self):
        slugs = {heading_slug(line.lstrip("#").strip()) for line in unfenced_lines(self.runtime) if line.startswith("#")}
        broken = []
        for path in sorted((ROOT / "skills").rglob("*.md")):
            for fragment in RUNTIME_LINK.findall(path.read_text()):
                if fragment not in slugs:
                    broken.append(f"{path.relative_to(ROOT)}#{fragment}")
        for fragment in re.findall(r"\]\(#([^)\s]+)\)", self.runtime):
            if fragment not in slugs:
                broken.append(f"pstack-runtime/SKILL.md#{fragment}")
        self.assertEqual(broken, [])
        self.assertEqual(heading_slug("Resolve and carry the mode"), "resolve-and-carry-the-mode")

    def test_runtime_has_one_modes_section_between_roles_and_isolation(self):
        headings = [line for line in unfenced_lines(self.runtime) if line.startswith("## ") or line.startswith("### ")]
        self.assertEqual(headings.count("## Modes"), 1)
        modes = headings.index("## Modes")
        self.assertLess(headings.index("## Roles"), modes)
        isolation = headings.index("## Isolation")
        self.assertEqual(headings[modes + 1:isolation], [
            "### Resolve and carry the mode",
            "### Light behavior",
            "### Never cut",
            "### Gate review",
            "### Announcement",
        ])
        self.assertIn("pass check <item> --sha <head> --json", self.runtime)

    def test_deadlines_and_delegation_step_4_carry_the_mode_lines(self):
        deadlines = self.runtime.split("## Deadlines", 1)[1].split("\n## ", 1)[0]
        self.assertIn(
            "A step that the brief's `Waived by mode:` line names is not a skip, "
            "because the mode removed it before the attempt started.",
            deadlines,
        )
        step = next(line for line in self.runtime.splitlines() if line.startswith("4. A child starts with only its brief."))
        for needed in ("roles.py mode --cwd", "Write no `Playbook:` line of your own", "--brief-mode"):
            self.assertIn(needed, step)

    def test_opening_a_pr_gates_light_prs_before_the_forge(self):
        text = (ROOT / "skills/poteto-mode/playbooks/opening-a-pr.md").read_text()
        blocks = text.split("\n\n")
        lead = [block.split(" ", 1)[0] for block in blocks]
        self.assertLess(lead.index("**Descriptions.**"), lead.index("**Gate.**"))
        self.assertLess(lead.index("**Gate.**"), lead.index("**Forge.**"))
        self.assertIn("(../../pstack-runtime/SKILL.md#gate-review)", blocks[lead.index("**Gate.**")])
        child = next(block for block in blocks if block.startswith("A child task that opens a PR"))
        self.assertIn("that child runs the **Gate** paragraph above in place of `interrogate` and `/no-comments`.", child)
        self.assertIn("Run `/no-comments` before review.", text)

    def test_gate_contract_is_literal(self):
        self.assertEqual(gate_contract(self.runtime), GATE_CONTRACT)

    def test_seat_rule_is_literal(self):
        self.assertEqual(seat_rule(self.runtime), SEAT_RULE)

    def test_every_owner_row_carries_the_seat_rule(self):
        rows = [row for row in light_behavior_rows(self.runtime) if "mode lines" in row]
        self.assertGreaterEqual(len(rows), 4)
        for row in rows:
            self.assertIn(
                "the seat rule from [Resolve and carry the mode](#resolve-and-carry-the-mode)",
                row,
            )

    def test_child_facing_light_rows(self):
        self.assertIn(
            "Its brief lists every `threadId` that `t3_thread_list` returns in the window, across every page. The parent filters and samples none",
            light_row(self.runtime, "`automate-me`"),
        )
        self.assertIn("pass `--session-mode full`", light_row(self.runtime, "`reflect`"))
        verification = light_row(self.runtime, "Multi-phase verification")
        self.assertIn("every **Verify, live** lane box that drives its surface", verification)
        self.assertIn("Launch no perf lane.", verification)
        self.assertIn("(#gate-review)", verification)

    def test_explicit_reflect_names_session_full_at_both_flag_sites(self):
        roles = self.runtime.split("### Where roles live", 1)[1].split("\n### ", 1)[0]
        paragraph = next(block for block in roles.split("\n\n") if block.startswith("When the brief this call seats"))
        self.assertIn(
            "except for a user's explicit reflect, which passes `--session-mode full`",
            paragraph,
        )
        resolve = self.runtime.split("### Resolve and carry the mode", 1)[1].split("\n### ", 1)[0]
        self.assertIn("except the explicit reflect below", resolve)
        self.assertIn(
            "A user's explicit reflect passes `--session-mode full` on every `roles.py show` call",
            resolve,
        )

    def test_automate_me_brief_lists_every_assigned_thread(self):
        text = (ROOT / "skills/automate-me/SKILL.md").read_text()
        self.assertIn("brief lists every `threadId` in its assignment", text)
        self.assertIn("An assignment is never a sample or a pick of the relevant threads.", text)
        self.assertNotIn("gets its slice", text)

    def test_autopilot_owner_message_carries_the_seat_rule(self):
        text = (ROOT / "skills/poteto-mode/playbooks/autopilot-full.md").read_text()
        self.assertIn(
            "Each owner `message`, including a replacement's, carries the mode lines and the seat rule "
            "from [Resolve and carry the mode](../../pstack-runtime/SKILL.md#resolve-and-carry-the-mode).",
            text,
        )

    def test_gate_brief_pastes_persona_then_contract(self):
        paragraph = brief_paragraph(self.runtime)
        self.assertIn("Paste the body of `agents/comment-sicko.md` unchanged", paragraph)
        self.assertIn("paste the gate contract below unchanged", paragraph)
        self.assertNotIn("and ask for that skill's checks", self.runtime)

    def test_every_gate_review_row_links_gate_review(self):
        for row in light_behavior_rows(self.runtime):
            if "gate review" not in row and "is the gate" not in row:
                continue
            spawn = row.split("|")[1].strip()
            self.assertIn("(#gate-review)", row, spawn)

    def test_full_mode_persona_keeps_investigation(self):
        persona = (ROOT / "skills/pstack-runtime/agents/comment-sicko.md").read_text()
        self.assertIn("I run the **how** skill, the **why** skill, or both", persona)


class BuildTest(unittest.TestCase):
    def test_generated_tree_passes_check(self):
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory) / "skills"
            result = subprocess.run([sys.executable, str(ROOT / "scripts/build.py"), "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(check.check_tree(out), [])
            self.assertTrue((out / "pstack-runtime/scripts/roles.py").exists())
            for skill_md in out.glob("*/SKILL.md"):
                self.assertNotIn("disable-model-invocation", skill_md.read_text().split("---")[1], skill_md)

    def test_replace_tree_recovers_an_interrupted_swap_before_copying(self):
        import build
        from unittest import mock
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            (base / "dest.outgoing").mkdir()
            (base / "dest.outgoing/old").write_text("old")
            (base / "src").mkdir()
            with mock.patch.object(build.shutil, "copytree", side_effect=OSError("disk full")):
                with self.assertRaises(OSError):
                    build.replace_tree(base / "src", base / "dest")
            self.assertEqual((base / "dest/old").read_text(), "old")

    def test_check_rejects_invalid_yaml_frontmatter(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "demo"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: demo\ndescription: [unterminated\n---\n\nbody\n")
            self.assertTrue(any("not valid YAML" in finding for finding in check.check_tree(directory)))

    def test_catalog_lists_every_skill_and_playbook(self):
        import catalog
        text = catalog.render(ROOT / "skills")
        for skill_md in (ROOT / "skills").glob("*/SKILL.md"):
            self.assertIn(f"[`{skill_md.parent.name}`]", text)
        self.assertIn("(../skills/poteto-mode/playbooks/bug-fix.md)", text)

    def test_check_flags_cursor_leftovers(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "demo"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n\nSpawn with `subagent_type: generalPurpose`.\n")
            findings = check.check_tree(directory)
        self.assertTrue(any("subagent_type" in finding for finding in findings))

    def test_check_requires_watch_tool_names_on_the_runtime_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "pstack-runtime"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: pstack-runtime\ndescription: d\n---\n\nNo watch here.\n")
            findings = check.check_tree(directory)
            self.assertIn("pstack-runtime/SKILL.md: missing watch_pull_request", findings)
            self.assertIn("pstack-runtime/SKILL.md: missing unwatch_pull_request", findings)
            (skill / "SKILL.md").write_text(
                "---\nname: pstack-runtime\ndescription: d\n---\n\n"
                "Call `watch_pull_request`. Call `unwatch_pull_request`.\n"
            )
            findings = check.check_tree(directory)
        self.assertFalse(any("missing watch" in finding or "missing unwatch" in finding for finding in findings))

    def test_check_requires_the_watch_tool_and_version_on_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "setup-pstack"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: setup-pstack\ndescription: d\n---\n\nNo watch here.\n")
            findings = check.check_tree(directory)
            self.assertIn("setup-pstack/SKILL.md: missing watch_pull_request", findings)
            self.assertIn("setup-pstack/SKILL.md: missing 0.0.46-nightly.20261005.2702", findings)
            (skill / "SKILL.md").write_text(
                "---\nname: setup-pstack\ndescription: d\n---\n\n"
                "Call `watch_pull_request`. T3 Code 0.0.46-nightly.20261005.2702 or later.\n"
            )
            findings = check.check_tree(directory)
        self.assertFalse(any("missing watch_pull_request" in finding or "missing 0.0.46" in finding for finding in findings))

    def test_check_rejects_the_cursor_xhigh_slug(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "demo"
            skill.mkdir()
            (skill / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n\nUse claude-opus-5-5-xhigh.\n")
            findings = check.check_tree(directory)
        self.assertTrue(any("claude-opus-5-5-xhigh" in finding for finding in findings))

    def test_check_rejects_an_indented_catalog_heredoc_closer(self):
        bad = "\n".join([
            "---",
            "name: demo",
            "description: d",
            "---",
            "",
            "```bash",
            "python3 tool <<'JSON'",
            '{"ok": true}',
            "  JSON",
            "```",
            "",
        ])
        good = "\n".join([
            "---",
            "name: demo",
            "description: d",
            "---",
            "",
            "```bash",
            "python3 tool <<'JSON'",
            '{"ok": true}',
            "JSON",
            "```",
            "",
        ])
        plain = "\n".join([
            "---",
            "name: demo",
            "description: d",
            "---",
            "",
            "  JSON",
            "",
        ])
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "demo"
            skill.mkdir()
            (skill / "SKILL.md").write_text(bad)
            findings = check.check_tree(directory)
        self.assertIn(
            "demo/SKILL.md:9: catalog heredoc closer JSON is indented. Put JSON at column 0",
            findings,
        )
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "demo"
            skill.mkdir()
            (skill / "SKILL.md").write_text(good)
            findings = check.check_tree(directory)
        self.assertFalse(any("heredoc closer" in finding for finding in findings))
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "demo"
            skill.mkdir()
            (skill / "SKILL.md").write_text(plain)
            findings = check.check_tree(directory)
        self.assertFalse(any("heredoc closer" in finding for finding in findings))

    def test_check_scopes_the_catalog_heredoc_closer_to_its_body(self):
        text = "\n".join([
            "---",
            "name: demo",
            "description: d",
            "---",
            "",
            "  JSON",
            "```bash",
            "python3 tool <<'JSON'",
            '{"name": "JSON"}',
            "JSON ",
            "JSON\t",
            "  JSON",
            "JSON",
            "```",
            "",
            "  JSON",
            "",
        ])
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "demo"
            skill.mkdir()
            (skill / "SKILL.md").write_text(text)
            findings = check.check_tree(directory)
        self.assertEqual(findings, [
            "demo/SKILL.md:10: catalog heredoc closer JSON has trailing whitespace. The closer is JSON with nothing after it",
            "demo/SKILL.md:11: catalog heredoc closer JSON has trailing whitespace. The closer is JSON with nothing after it",
            "demo/SKILL.md:12: catalog heredoc closer JSON is indented. Put JSON at column 0",
        ])

    def light_findings(self, rel, body):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / rel
            path.parent.mkdir(parents=True)
            name = rel.split("/", 1)[0]
            path.write_text(f"---\nname: {name}\ndescription: d\n---\n\n{body}\n" if rel.endswith("SKILL.md") else body)
            return [finding for finding in check.check_tree(directory) if "light" in finding]

    def test_check_rejects_a_pasted_waiver_table(self):
        header = "| Playbook | `first` | `fix` and `bounce` |"
        findings = self.light_findings("demo/SKILL.md", "\n".join([
            header,
            "| --- | --- | --- |",
            "| Feature | Arena, Interrogate, Comment Sicko | How, Architect, Arena, Interrogate, Comment Sicko |",
        ]))
        self.assertIn(
            f"demo/SKILL.md:6: light table restated. Link pstack-runtime/SKILL.md#modes instead of pasting it: {header}",
            findings,
        )

    def test_check_rejects_a_census_with_a_light_column(self):
        header = "| Census row | Full | Light | Kind |"
        findings = self.light_findings("demo/SKILL.md", f"{header}\n| --- | --- | --- | --- |")
        self.assertEqual(findings, [
            f"demo/SKILL.md:6: light table restated. Link pstack-runtime/SKILL.md#modes instead of pasting it: {header}",
        ])

    def test_check_rejects_light_mode_prose_without_the_runtime_link(self):
        findings = self.light_findings("demo/SKILL.md", "In light mode, launch at most 3 workers.")
        self.assertEqual(findings, [
            "demo/SKILL.md:6: names light mode without a link to the runtime's Modes section. "
            "Link pstack-runtime/SKILL.md#modes: In light mode, launch at most 3 workers.",
        ])

    def test_check_accepts_the_modes_pointer(self):
        pointer = (
            "[The runtime's Modes section](../pstack-runtime/SKILL.md#modes) sets the mode lines "
            "of every brief this skill writes and how its spawns run in light mode."
        )
        self.assertEqual(self.light_findings("demo/SKILL.md", pointer), [])

    def test_check_lets_the_runtime_hold_the_light_table(self):
        body = "\n".join([
            "Call `watch_pull_request`. Call `unwatch_pull_request`.",
            "",
            "| Spawn | Light behavior |",
            "| --- | --- |",
            "| Feature | Arena, Interrogate, Comment Sicko |",
            "",
            "In light mode, launch at most 3 workers.",
        ])
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "pstack-runtime"
            skill.mkdir()
            (skill / "SKILL.md").write_text(f"---\nname: pstack-runtime\ndescription: d\n---\n\n{body}\n")
            self.assertEqual(check.check_tree(directory), [])

    def test_check_ignores_waiver_names_outside_markdown(self):
        findings = self.light_findings("demo/scripts/x.py", 'ROW = ("Arena", "Interrogate", "Comment Sicko")\n')
        self.assertEqual(findings, [])

    def test_check_accepts_an_unrelated_playbook_table(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "demo"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: demo\ndescription: d\n---\n\n| Playbook | Purpose |\n| --- | --- |\n| Feature | New behavior |\n"
            )
            self.assertEqual(check.check_tree(directory), [])


def fragment_name(branch):
    return branch.replace("%", "%25").replace("/", "%2F") + ".md"


def fragment_holds_bullets(lines):
    open_bullet = False
    for line in lines:
        if line.startswith("- ") and line[2:].strip():
            open_bullet = True
            continue
        if open_bullet and (line.startswith(" ") or line.startswith("\t")) and line.strip():
            continue
        return False
    return open_bullet


def changelog_findings(root):
    findings = []
    changelog = root / "CHANGELOG.md"
    if changelog.is_file():
        for line in changelog.read_text().splitlines():
            if line.strip() == "## Unreleased":
                findings.append(
                    "CHANGELOG.md has a ## Unreleased heading. Write the bullet under changes/."
                )
                break
    changes = root / "changes"
    if not changes.is_dir():
        return findings
    for path in sorted(p for p in changes.rglob("*") if p.is_file()):
        relative = path.relative_to(changes).as_posix()
        if "/" in relative:
            findings.append(f"changes/{relative} sits in a subdirectory. changes/ is flat.")
            continue
        if not fragment_holds_bullets(path.read_text().splitlines()):
            findings.append(f"changes/{relative} holds a line that is not a bullet.")
    return findings


def _git(repo, *args):
    return subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "LC_ALL": "C",
        },
    ).stdout


def release_bullets(repo):
    log = _git(
        repo,
        "log",
        "--reverse",
        "--diff-filter=A",
        "--format=",
        "--name-only",
        "--",
        "changes/",
    )
    order = []
    for line in log.splitlines():
        if not line.startswith("changes/") or line.count("/") != 1 or not (repo / line).is_file():
            continue
        if line in order:
            order.remove(line)
        order.append(line)
    bullets = []
    for relative in order:
        bullets.extend((repo / relative).read_text().splitlines())
    return bullets


class ChangelogTest(unittest.TestCase):
    def test_fragment_name_encodes_percent_before_slash(self):
        self.assertEqual(fragment_name("docs/a"), "docs%2Fa.md")
        self.assertEqual(fragment_name("docs-a"), "docs-a.md")
        self.assertEqual(fragment_name("a/b%c"), "a%2Fb%25c.md")

    def test_changelog_findings_name_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n\n- old\n")
            (root / "changes").mkdir()
            (root / "changes" / "note.md").write_text("Prose.\n")
            nested = root / "changes" / "nested"
            nested.mkdir()
            (nested / "x.md").write_text("- hidden\n")
            self.assertEqual(changelog_findings(root), [
                "CHANGELOG.md has a ## Unreleased heading. Write the bullet under changes/.",
                "changes/nested/x.md sits in a subdirectory. changes/ is flat.",
                "changes/note.md holds a line that is not a bullet.",
            ])
            (root / "CHANGELOG.md").write_text("# Changelog\n")
            (root / "changes" / "nested" / "x.md").unlink()
            nested.rmdir()
            (root / "changes" / "note.md").write_text("- First.\n- Second.\n")
            self.assertEqual(changelog_findings(root), [])
            (root / "changes" / "note.md").write_text(
                "- A user-facing change spans\n  two lines in the same bullet.\n"
            )
            self.assertEqual(changelog_findings(root), [])
            (root / "changes" / "note.md").write_text(
                "- A user-facing change spans\nthen prose on its own line.\n"
            )
            self.assertEqual(changelog_findings(root), [
                "changes/note.md holds a line that is not a bullet.",
            ])
            (root / "changes" / "note.md").unlink()
            self.assertEqual(changelog_findings(root), [])
            shutil.rmtree(root / "changes")
            self.assertEqual(changelog_findings(root), [])

    def test_repo_changelog_has_no_unreleased_heading(self):
        findings = changelog_findings(ROOT)
        self.assertEqual(findings, [], "\n".join(findings) or "Write bullets under changes/.")
        contributing = (ROOT / "CONTRIBUTING.md").read_text()
        self.assertIn(
            "git log --reverse --diff-filter=A --format= --name-only -- changes/",
            contributing,
        )
        self.assertNotIn("Add a line under Unreleased", contributing)
        self.assertNotIn("Each bullet is one line", contributing)
        self.assertIn("Indent a continuation line under that bullet.", contributing)
        self.assertIn("docs/guide.md", contributing)
        self.assertIn("one docs change", contributing)

    def test_release_cut_matches_the_fragments_that_still_exist(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            _git(repo, "init", "-q", "-b", "main")
            (repo / "changes").mkdir()
            (repo / "changes" / "first.md").write_text("- alpha\n")
            _git(repo, "add", "changes")
            _git(repo, "commit", "-qm", "first")
            (repo / "changes" / "second.md").write_text("- beta\n")
            _git(repo, "add", "changes")
            _git(repo, "commit", "-qm", "second")
            _git(repo, "rm", "-q", "changes/first.md")
            _git(repo, "commit", "-qm", "cut")
            (repo / "changes" / "first.md").write_text(
                "- alpha again\n  kept on the next line.\n"
            )
            _git(repo, "add", "changes")
            _git(repo, "commit", "-qm", "first again")
            bullets = release_bullets(repo)
            self.assertEqual(bullets, [
                "- beta",
                "- alpha again",
                "  kept on the next line.",
            ])
            section = "## 0.3.0 (2026-10-06)\n\n" + "\n".join(bullets) + "\n"
            held = "".join(
                (repo / name).read_text()
                for name in ("changes/second.md", "changes/first.md")
            )
            self.assertEqual(section, "## 0.3.0 (2026-10-06)\n\n" + held)
            self.assertNotIn("- alpha\n", section)
            self.assertIn("  kept on the next line.\n", section)
            (repo / "CHANGELOG.md").write_text("# Changelog\n\n" + section)
            _git(repo, "add", "CHANGELOG.md")
            _git(repo, "rm", "-q", "changes/first.md", "changes/second.md")
            _git(repo, "commit", "-qm", "0.3.0")
            self.assertEqual(
                _git(repo, "show", "HEAD^:changes/first.md"),
                "- alpha again\n  kept on the next line.\n",
            )
            self.assertEqual(
                _git(repo, "show", "HEAD:CHANGELOG.md"),
                "# Changelog\n\n## 0.3.0 (2026-10-06)\n\n"
                "- beta\n- alpha again\n  kept on the next line.\n",
            )
            names = [
                line for line in _git(
                    repo, "diff-tree", "--no-commit-id", "--name-status",
                    "--no-renames", "-r", "HEAD",
                ).splitlines()
                if line
            ]
            self.assertEqual(names, [
                "A\tCHANGELOG.md",
                "D\tchanges/first.md",
                "D\tchanges/second.md",
            ])
            self.assertEqual(release_bullets(repo), [])


AUDIT = ROOT / "t3/overrides/poteto-mode/scripts/worktree-audit.sh"
PREVIEW_TOOLS = (
    "preview_hover",
    "preview_drag",
    "preview_select",
    "preview_upload",
    "preview_dialog",
)


def _init_repo(path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "audit@example.com"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "audit"], check=True)
    (path / "f").write_text("a\n")
    subprocess.run(["git", "-C", str(path), "add", "f"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "init"], check=True)


def _add_worktree(repo, path, branch):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "-q", str(path), "-b", branch],
        check=True,
    )


class WorktreeAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        _init_repo(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def _audit(self, *args, **env):
        run_env = os.environ.copy()
        for key in ("T3CODE_HOME", "T3_HOME", "T3_WORKTREES"):
            run_env.pop(key, None)
        run_env.update(env)
        completed = subprocess.run(
            [str(AUDIT), str(self.repo), *args],
            capture_output=True,
            text=True,
            env=run_env,
            timeout=60,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        marks = {}
        lines = [line for line in completed.stdout.splitlines() if line]
        self.assertGreaterEqual(len(lines), 2, completed.stdout)
        for line in lines[1:]:
            cols = line.split("\t")
            self.assertEqual(len(cols), 10, line)
            marks[cols[9]] = cols[7]
        return marks

    def test_configured_locations_count_and_bad_ones_do_not(self):
        t3_home = self.root / "code-home"
        other_home = self.root / "other-home"
        default = t3_home / "worktrees" / "proj" / "wt-default"
        custom = self.root / "home" / "custom" / "wt-custom"
        previous = self.root / "old" / "wt-old"
        stray = self.root / "stray" / "wt-stray"
        _add_worktree(self.repo, default, "b-default")
        _add_worktree(self.repo, custom, "b-custom")
        _add_worktree(self.repo, previous, "b-old")
        _add_worktree(self.repo, stray, "b-stray")
        (t3_home / "userdata").mkdir(parents=True)
        (t3_home / "userdata" / "settings.json").write_text(json.dumps({
            "worktreesDirectory": "~/custom",
            "previousWorktreesDirectories": [str(previous.parent), "/", "relative/nope"],
        }))
        marks = self._audit(
            T3CODE_HOME=str(t3_home),
            T3_HOME=str(other_home),
            HOME=str(self.root / "home"),
        )
        self.assertEqual(marks[str(default)], "yes")
        self.assertEqual(marks[str(custom)], "yes")
        self.assertEqual(marks[str(previous)], "yes")
        self.assertEqual(marks[str(stray)], "no")

    def test_flag_and_env_replace_the_configured_directory(self):
        t3_home = self.root / "t3home"
        default = t3_home / "worktrees" / "proj" / "wt-default"
        chosen = self.root / "chosen" / "wt"
        decoy = self.root / "decoy" / "wt"
        _add_worktree(self.repo, default, "b-default")
        _add_worktree(self.repo, chosen, "b-chosen")
        _add_worktree(self.repo, decoy, "b-decoy")
        (t3_home / "userdata").mkdir(parents=True)
        (t3_home / "userdata" / "settings.json").write_text(json.dumps({
            "worktreesDirectory": str(decoy.parent),
        }))
        marks = self._audit(
            "--t3-worktrees", str(chosen.parent),
            T3_HOME=str(t3_home),
            T3_WORKTREES=str(decoy.parent),
        )
        self.assertEqual(marks[str(default)], "yes")
        self.assertEqual(marks[str(chosen)], "yes")
        self.assertEqual(marks[str(decoy)], "no")

    def _parser_path(self, parser):
        bindir = self.root / f"bin-{parser}"
        bindir.mkdir()
        for cmd in (
            "bash", "git", "sed", "head", "date", "awk", "mktemp", "rm",
            "sort", "du", "grep", parser,
        ):
            found = shutil.which(cmd)
            if found is None:
                self.skipTest(f"{cmd} is not installed")
            (bindir / cmd).symlink_to(found)
        return str(bindir)

    def test_symlinked_setting_matches_the_physical_worktree(self):
        t3_home = self.root / "t3home"
        custom = self.root / "custom"
        alias = self.root / "alias"
        root_link = self.root / "root-link"
        direct = custom / "wt"
        via_alias = alias / "created-via-alias"
        outside = self.root / "outside" / "wt"
        default = t3_home / "worktrees" / "wt"
        _add_worktree(self.repo, direct, "b-direct")
        alias.symlink_to(custom, target_is_directory=True)
        _add_worktree(self.repo, via_alias, "b-alias")
        _add_worktree(self.repo, outside, "b-out")
        _add_worktree(self.repo, default, "b-default")
        root_link.symlink_to(Path("/"))
        (t3_home / "userdata").mkdir(parents=True)
        settings = t3_home / "userdata" / "settings.json"
        settings.write_text(json.dumps({"worktreesDirectory": str(alias)}))
        marks = self._audit(T3CODE_HOME=str(t3_home))
        self.assertEqual(marks[str(direct)], "yes")
        self.assertEqual(marks[str(custom / "created-via-alias")], "yes")
        self.assertEqual(marks[str(default)], "yes")
        self.assertEqual(marks[str(outside)], "no")

        settings.write_text(json.dumps({"worktreesDirectory": str(root_link)}))
        marks = self._audit(T3CODE_HOME=str(t3_home))
        self.assertEqual(marks[str(outside)], "no")
        self.assertEqual(marks[str(default)], "yes")
        self.assertEqual(marks[str(direct)], "no")

    def test_bad_previous_field_is_ignored_by_each_parser(self):
        t3_home = self.root / "t3home"
        custom = self.root / "custom" / "wt"
        outside = self.root / "outside" / "wt"
        previous = self.root / "previous" / "wt"
        default = t3_home / "worktrees" / "wt"
        for path, branch in (
            (custom, "b-custom"),
            (outside, "b-out"),
            (previous, "b-prev"),
            (default, "b-default"),
        ):
            _add_worktree(self.repo, path, branch)
        (t3_home / "userdata").mkdir(parents=True)
        settings = t3_home / "userdata" / "settings.json"
        bad_values = (
            {"oops": str(outside.parent)},
            "invalid",
            12,
            None,
            [1, {"oops": str(outside.parent)}, str(previous.parent)],
        )
        parsers = [name for name in ("jq", "python3") if shutil.which(name)]
        self.assertGreaterEqual(len(parsers), 1)
        for parser in parsers:
            tool_path = self._parser_path(parser)
            for value in bad_values:
                settings.write_text(json.dumps({
                    "worktreesDirectory": str(custom.parent),
                    "previousWorktreesDirectories": value,
                }))
                marks = self._audit(T3CODE_HOME=str(t3_home), PATH=tool_path)
                self.assertEqual(marks[str(custom)], "yes", (parser, value))
                self.assertEqual(marks[str(outside)], "no", (parser, value))
                self.assertEqual(marks[str(default)], "yes", (parser, value))
                expect_previous = "yes" if isinstance(value, list) else "no"
                self.assertEqual(marks[str(previous)], expect_previous, (parser, value))

    def test_padded_home_and_setting_count(self):
        t3_home = self.root / "t3home"
        home = self.root / "home"
        custom = self.root / "custom" / "wt"
        tilde_custom = home / "custom" / "wt"
        outside = self.root / "outside" / "wt"
        default = t3_home / "worktrees" / "wt"
        _add_worktree(self.repo, custom, "b-custom")
        _add_worktree(self.repo, tilde_custom, "b-tilde")
        _add_worktree(self.repo, outside, "b-out")
        _add_worktree(self.repo, default, "b-default")
        (t3_home / "userdata").mkdir(parents=True)
        settings = t3_home / "userdata" / "settings.json"
        settings.write_text(json.dumps({
            "worktreesDirectory": f"  {custom.parent}  ",
        }))
        marks = self._audit(T3CODE_HOME=f"  {t3_home}  ", HOME=str(home))
        self.assertEqual(marks[str(default)], "yes")
        self.assertEqual(marks[str(custom)], "yes")
        self.assertEqual(marks[str(outside)], "no")

        settings.write_text(json.dumps({"worktreesDirectory": "  ~/custom  "}))
        marks = self._audit(T3CODE_HOME=f"  {t3_home}  ", HOME=str(home))
        self.assertEqual(marks[str(tilde_custom)], "yes")
        self.assertEqual(marks[str(custom)], "no")

        marks = self._audit(T3CODE_HOME="   ", T3_HOME=str(t3_home), HOME=str(home))
        self.assertEqual(marks[str(default)], "yes")

    def test_javascript_whitespace_pad_counts_for_each_parser(self):
        t3_home = self.root / "t3home"
        custom = self.root / "custom" / "wt"
        outside = self.root / "outside" / "wt"
        default = t3_home / "worktrees" / "wt"
        _add_worktree(self.repo, custom, "b-custom")
        _add_worktree(self.repo, outside, "b-out")
        _add_worktree(self.repo, default, "b-default")
        (t3_home / "userdata").mkdir(parents=True)
        settings = t3_home / "userdata" / "settings.json"
        parsers = [name for name in ("jq", "python3") if shutil.which(name)]
        self.assertEqual(parsers, ["jq", "python3"])
        paths = {parser: self._parser_path(parser) for parser in parsers}
        for pad in ("\u00a0", "\ufeff"):
            for parser, tool_path in paths.items():
                label = (parser, hex(ord(pad)))
                settings.write_text(json.dumps({
                    "worktreesDirectory": f"{pad}{custom.parent}{pad}",
                }))
                marks = self._audit(T3CODE_HOME=str(t3_home), PATH=tool_path)
                self.assertEqual(marks[str(custom)], "yes", (*label, "setting"))
                self.assertEqual(marks[str(default)], "yes", (*label, "setting"))
                self.assertEqual(marks[str(outside)], "no", (*label, "setting"))

                settings.write_text(json.dumps({
                    "worktreesDirectory": str(custom.parent),
                }))
                marks = self._audit(
                    T3CODE_HOME=f"{pad}{t3_home}{pad}",
                    PATH=tool_path,
                )
                self.assertEqual(marks[str(custom)], "yes", (*label, "home"))
                self.assertEqual(marks[str(default)], "yes", (*label, "home"))
                self.assertEqual(marks[str(outside)], "no", (*label, "home"))

    def test_playbook_names_the_configured_worktree_location(self):
        text = (ROOT / "t3/overrides/poteto-mode/playbooks/worktree-cleanup.md").read_text()
        self.assertIn("worktreesDirectory", text)
        self.assertIn("--t3-worktrees", text)
        self.assertIn("T3_WORKTREES", text)
        self.assertIn("replaces those settings roots", text)


def runtime_section(start, end="\n## "):
    text = (ROOT / "t3/runtime.md").read_text()
    return text.split(start, 1)[1].split(end, 1)[0]


def runtime_bullet(section, prefix):
    return next(line for line in section.splitlines() if line.startswith(prefix))


def override_text(path):
    return (ROOT / "t3/overrides" / path).read_text()


def _context_catalog(provider_id, model_options):
    return {
        "providers": [{
            "providerInstanceId": provider_id,
            "canRunChildTask": True,
            "constraints": [],
            "models": [{"id": "claude-opus-5-5", "options": model_options}],
        }],
    }


_EFFORT_OPTION = {
    "id": "effort",
    "type": "select",
    "options": [{"id": "low"}, {"id": "medium"}, {"id": "high"}, {"id": "xhigh"}, {"id": "max"}],
}
_WINDOW_OPTION = {
    "id": "contextWindow",
    "type": "select",
    "options": [{"id": "300k"}, {"id": "1m"}],
}


class ThreadLifecycleDocTest(unittest.TestCase):
    def test_history_names_snooze_fields_and_filter(self):
        section = runtime_section("## History")
        for sentence in (
            "`t3_thread_list` and `t3_thread_read` report `snoozed` and `snoozedUntil`.",
            "Pass `snoozed: true` to `t3_thread_list` to find snoozed owners.",
            '`t3_thread_organize` with `action: "snooze"` requires `snoozedUntil`.',
            "A snoozed thread wakes early when it asks for something, fails, or completes.",
            "Snooze is a sidebar state.",
            "It is not a schedule, a completion, or a settle.",
            "Wait with `schedule_task` or `watch_pull_request`, never with `snoozedUntil`.",
        ):
            self.assertIn(sentence, section)

    def test_history_states_the_thread_link_in_a_form_check_accepts(self):
        section = runtime_section("## History")
        self.assertIn("whose target is `t3-thread://v1/<threadId>`", section)
        self.assertIn("Do not URL-encode it, decode its `%` escapes, or add an environment ID.", section)
        self.assertIn("carry no `link` field", section)
        launch = runtime_section("## Top-level threads")
        self.assertIn("Report it to the user as a thread link per [History](#history).", launch)
        self.assertEqual(check.LINK.findall("[t](t3-thread://v1/abc)"), ["t3-thread://v1/abc"])
        targets = check.LINK.findall((ROOT / "t3/runtime.md").read_text())
        self.assertFalse(any(target.startswith("t3-thread:") for target in targets))

    def test_self_settle_is_a_request_not_a_settle(self):
        section = runtime_section("## Pull request watching")
        for phrase in (
            "`settlesWhenTurnEnds: true`",
            "an accepted request, not a settled thread",
            "or a queued message, leaves the thread active",
            "a T3 restart before the turn ends drops the request",
            "Never settle an owner whose PR watch or `schedule_task` loop is still needed",
        ):
            self.assertIn(phrase, section)

    def test_isolation_names_the_settle_action(self):
        section = runtime_section("## Isolation")
        for phrase in (
            "T3 runs the first effective project action with `runOnSettle: true`",
            "A thread in the main checkout skips it.",
            "The effective list is the project's override, else the environment defaults.",
            "Actions in a repository `t3.json` count only once imported into project settings",
            "`t3_project_read` returns the project's saved `scripts`, which can differ from the effective list.",
            "Take `projectSettingsOverrides.<projectId>.defaultProjectScripts` when present, else `defaultProjectScripts`",
            "When `projectSettingsFolded` is not `true`, older saved lists still count",
            "never schedule a tick to watch for it",
            "T3 storage cleanup can remove that worktree after the thread ends.",
        ):
            self.assertIn(phrase, section)
        self.assertNotIn("Read `t3.json` before you settle", section)

    def test_local_state_does_not_promise_worktrees_persist(self):
        section = runtime_section("## Local state")
        self.assertNotIn("Pushed branches, worktrees, launched threads, and schedules persist.", section)
        self.assertIn("unless the project enables storage cleanup", section)
        self.assertIn("by squash or rebase at the worktree's head SHA", section)
        self.assertIn("check that `worktreePath` exists before you use a saved path", section)


class FixedContextWindowTest(unittest.TestCase):
    def _entry(self, provider_id, model_options, saved_options):
        seat = {"providerInstanceId": provider_id, "model": "claude-opus-5-5", "options": saved_options}
        catalog = _context_catalog(provider_id, model_options)
        return roles.resolve(config(**{"judgment and prose": [seat]}), catalog, ["judgment and prose"])["roles"]["judgment and prose"]

    def test_native_claude_5_drops_a_saved_context_window(self):
        entry = self._entry("claudeAgent", [_EFFORT_OPTION], {"effort": "xhigh", "contextWindow": "1m"})
        self.assertEqual(entry["seats"], [OPUS_SEAT])
        self.assertEqual(entry["notes"], ["dropped unknown options contextWindow"])
        setup = (ROOT / "t3/setup.md").read_text()
        self.assertIn("`dropped unknown options contextWindow`", setup)
        self.assertIn("0.0.46-nightly.20261008.2801", setup)

    def test_keeps_context_window_when_the_catalog_offers_it(self):
        saved = {"effort": "xhigh", "contextWindow": "1m"}
        entry = self._entry("claudeAgent", [_EFFORT_OPTION, _WINDOW_OPTION], saved)
        self.assertEqual(entry["seats"], [{"providerInstanceId": "claudeAgent", "model": "claude-opus-5-5", "options": saved}])
        self.assertNotIn("notes", entry)
        setup = (ROOT / "t3/setup.md").read_text()
        self.assertIn("Write `contextWindow` only for a model whose catalog entry offers it.", setup)

    def test_cursor_claude_5_keeps_a_saved_context_window(self):
        saved = {"effort": "xhigh", "contextWindow": "300k"}
        entry = self._entry("cursor", [_EFFORT_OPTION, _WINDOW_OPTION], saved)
        self.assertEqual(entry["seats"], [{"providerInstanceId": "cursor", "model": "claude-opus-5-5", "options": saved}])
        self.assertNotIn("notes", entry)
        self.assertEqual(entry["seats"][0]["options"]["contextWindow"], "300k")
        setup = (ROOT / "t3/setup.md").read_text()
        self.assertIn("Cursor's Claude 5 models still offer it.", setup)

class LaunchingSkillTestDocTest(unittest.TestCase):
    def test_haiku_section_send_a_seat_launching_test_through_launches_seats(self):
        section = runtime_section("### Claude Haiku 5.5")
        self.assertIn('`roles.py show --role "skill tests" --launches-seats`', section)
        self.assertIn("never cursor", section)
        self.assertIn("cannot launch seats", section)
        self.assertIn("sends `target.options` as a JSON string", section)
        self.assertIn(roles.HAIKU_BRIEF[0], section)
        author = (ROOT / "t3/added/pstack-author-skill/SKILL.md").read_text()
        self.assertIn("--launches-seats", author)

    def test_delegation_step_4_pastes_haiku_brief_and_the_modes_bullet_does_not(self):
        text = (ROOT / "t3/runtime.md").read_text()
        step = text.split("4. A child starts with only its brief.", 1)[1].split("\n5. Collect results.", 1)[0]
        self.assertIn(
            "When the role entry `roles.py show` printed for the child's seat has `haikuBrief`, "
            "paste its paragraphs unchanged, in order, at the end of the brief, "
            "per [Claude Haiku 5.5](#claude-haiku-55).",
            step,
        )
        modes = runtime_section("## Modes")
        bullet = next(
            line for line in modes.splitlines()
            if line.startswith("- A code delegate's brief passes `--playbook <name> --attempt <kind>`")
        )
        self.assertNotIn("haikuBrief", bullet)


class MuseDocTest(unittest.TestCase):
    def test_runtime_names_muse_and_limits_its_modes(self):
        runtime = (ROOT / "t3/runtime.md").read_text()
        intro = next(line for line in runtime.splitlines() if "Every provider T3 drives" in line)
        self.assertIn("OpenCode, Muse, ACP agents", intro)
        permissions = runtime_section("### Permissions", "\n### ")
        self.assertIn("Muse supports only `approval-required` and `full-access`.", permissions)
        self.assertIn("Read `runtimeMode` from `orchestrator_capabilities` before you seat Muse.", permissions)
        self.assertIn('replace the Muse seat with `"inherit"` per [Fallback](#fallback)', permissions)
        self.assertIn("never lower it", permissions)

    def test_skill_locations_exclude_muse_from_the_picker(self):
        section = runtime_section("## Skill locations")
        self.assertIn("except Muse's", section)
        self.assertIn("`muse skills`", section)

    def test_setup_does_not_treat_a_cached_muse_catalog_as_proof(self):
        text = (ROOT / "t3/setup.md").read_text()
        step1 = text.split("### 1. Check the host", 1)[1].split("\n### 2. ", 1)[0]
        self.assertIn("does not prove a Muse seat works", step1)
        self.assertIn('`driverKind: "muse"`', step1)
        step5 = text.split("### 5. Verify", 1)[1].split("\n### 6. ", 1)[0]
        self.assertIn("does not prove a Muse child can work under this thread's runtime mode", step5)
        self.assertIn("(../pstack-runtime/SKILL.md#permissions)", step5)


class PreviewToolDocTest(unittest.TestCase):
    def test_runtime_names_hover_drag_select_upload_and_dialog(self):
        text = (ROOT / "t3/runtime.md").read_text()
        row = next(line for line in text.splitlines() if "control-ui, browser MCP" in line)
        bullet = next(line for line in text.splitlines() if line.startswith("- Web or Electron UI:"))
        for name in PREVIEW_TOOLS:
            self.assertIn(name, row)
            self.assertIn(name, bullet)


class StalledChildDocTest(unittest.TestCase):
    def test_delegation_step_5_bounds_an_open_child(self):
        text = (ROOT / "t3/runtime.md").read_text()
        step = text.split("5. Collect results.", 1)[1].split("6. You own every child's output.", 1)[0]
        self.assertIn("t3_thread_wait", step)
        self.assertIn("timeoutMs: 300000", step)
        self.assertIn("does not end its turn while a child is open", step)

    def test_delegation_step_5_rechecks_a_final_result_after_two_minutes(self):
        step = runtime_section("5. Collect results.", "\n6. You own")
        ten = "A child with no new item for 10 minutes is stalled."
        two = "no pending tool or child run, and no new activity for two minutes is stalled."
        for phrase in (
            two,
            "A message that says more work follows does not hold the result.",
            "After you see that message while the child's run is still open",
            "with `timeoutMs: 120000`",
            "only when the wait timed out, `workState` is still `working`, "
            "that message is still the last item, and no tool or child run is pending.",
            "Otherwise the 10-minute rule above decides that child.",
            ten,
        ):
            self.assertIn(phrase, step)
        self.assertLess(step.index(ten), step.index(two))

    def test_delegation_step_5_waits_out_an_ended_run(self):
        step = runtime_section("5. Collect results.", "\n6. You own")
        two = "no pending tool or child run, and no new activity for two minutes is stalled."
        ended = "A child's run can end while its task stays open."
        now = "If you need a result now"
        for phrase in (
            ended,
            "returns at once, because an idle thread returns immediately",
            "`waiting_for_children`",
            "Read the `activeRunId` of the `parentThreadId` from `orchestrator_capabilities` with `t3_thread_read`, and pass them as `threadId` and `runId`.",
            "Without `runId`, the call picks this thread's latest run, which can be a queued run already cancelled, and returns at once.",
            "returns `timedOut: true` after 120 seconds",
            "Never wait with a shell `sleep`",
            "a `task_status` check does not",
            "because the two-minute rule above needs an open run",
            "Count 10 minutes from the child's last activity item.",
        ):
            self.assertIn(phrase, step)
        self.assertLess(step.index(two), step.index(ended))
        self.assertLess(step.index(ended), step.index(now))

    def test_delegation_step_5_holds_against_the_delegate_task_tool_text(self):
        step = runtime_section("5. Collect results.", "\n6. You own")
        stay = "does not end its turn while a child is open"
        holds = "This holds even though the `delegate_task` tool text says to end the turn."
        self.assertIn(holds, step)
        self.assertLess(step.index(stay), step.index(holds))

    def test_failure_handling_keeps_the_two_minute_clock_out(self):
        section = runtime_section("### Failure handling", "### Fresh children by default")
        self.assertNotIn("two minutes", section)
        self.assertNotIn("120000", section)
        self.assertIn("holds the result the brief asked for", section)

    def test_permissions_never_lowers_runtime_mode(self):
        text = (ROOT / "t3/runtime.md").read_text()
        section = text.split("### Permissions", 1)[1].split("### Failure handling", 1)[0]
        self.assertIn("never lower it", section)

    def test_failure_handling_names_a_stalled_child(self):
        text = (ROOT / "t3/runtime.md").read_text()
        section = text.split("### Failure handling", 1)[1].split("### Fresh children by default", 1)[0]
        self.assertIn("A stalled child", section)

    def test_no_source_tells_a_parent_to_end_its_turn_on_an_open_child(self):
        unbounded = re.compile(r"completion notifications? wakes?|let (?:each|the) completion|end the turn rather than wait"
                               r"|`mode: \"async\"`,? and end the turn")
        found = [f"{path.relative_to(ROOT)}:{number}"
                 for path in sorted((ROOT / "t3").rglob("*.md"))
                 for number, line in enumerate(path.read_text().splitlines(), 1) if unbounded.search(line)]
        self.assertEqual(found, [])

    def test_routed_skills_collect_children_per_delegation_step_5(self):
        sources = {
            "how/SKILL.md": "../pstack-runtime", "arena/SKILL.md": "../pstack-runtime",
            "interrogate/SKILL.md": "../pstack-runtime", "swarm/SKILL.md": "../pstack-runtime",
            "why/SKILL.md": "../pstack-runtime", "no-comments/SKILL.md": "../pstack-runtime",
            "poteto-mode/playbooks/orchestrate.md": "../../pstack-runtime",
            "poteto-mode/playbooks/feature.md": "../../pstack-runtime",
            "poteto-mode/playbooks/bug-fix.md": "../../pstack-runtime",
            "poteto-mode/playbooks/refactoring.md": "../../pstack-runtime",
            "poteto-mode/playbooks/perf-issue.md": "../../pstack-runtime",
            "poteto-mode/playbooks/hillclimb.md": "../../pstack-runtime",
        }
        missing = [name for name, runtime in sources.items()
                   if f"Delegation step 5]({runtime}/SKILL.md#delegation)" not in (ROOT / "t3/overrides" / name).read_text()]
        self.assertEqual(missing, [])

    def test_failure_handling_relaunches_a_usage_limit_on_the_backup_ladder(self):
        section = runtime_section("### Failure handling", "\n### ")
        self.assertIn("roles.py backup", section)
        for decision in ("relaunch", "panel", "park", "not-usage-limit"):
            self.assertIn(f"`{decision}`", section)
        parks = "When every backup family is an author family, the command parks."
        panel = "For a `verifiers` seat with `review backups` set, the command prints `panel` instead."
        for phrase in (
            "The command prints `relaunch`, `panel`, `park`, or `not-usage-limit`.",
            panel,
            "a stable `clientRequestId` ending in `-panel-<n>`",
            "Wait until every member is terminal, even after two pass.",
            'runs this command with `--role "review backups"`, which parks it, and it counts as no pass.',
            "A member that fails otherwise respawns once.",
            "Land only if no reviewer reproduces a blocker and at least two of the panel pass.",
            "With `review backups` unset, or fewer than two usable seats, the command prints `park`.",
        ):
            self.assertIn(phrase, section)
        self.assertLess(section.index(parks), section.index(panel))
        self.assertIn("Backup never selects Codex or Cursor.", section)
        self.assertIn("Codex stays the default reviewer.", section)
        self.assertIn("A limit on `claudeAgent` parks a worker.", section)
        self.assertIn("`cursor/claude-opus-5-5`", section)
        self.assertIn("each code delegate's model", section)
        self.assertIn("`--resume` reads no error text.", section)
        self.assertIn("`grok-4.7` on `grok`", section)
        self.assertIn("--resume", section)
        self.assertIn("roles.py backup --cwd", section)
        self.assertIn("```bash", section)
        self.assertNotIn("A Claude worker parks.", section)
        self.assertIn("A panel relaunches the failed seat and says when a family repeats.", section)
        sentences = re.split(r"(?<=\.)\s+", section)

        def named_roles(sentence):
            return {name for name in re.findall(r"`([^`]+)`", sentence) if name in roles.ROLES}

        sonnet = next(sentence for sentence in sentences if "claude-sonnet-5-5" in sentence)
        reviewers = next(sentence for sentence in sentences if "skipping every author's family" in sentence)
        self.assertEqual(named_roles(sonnet), roles.LIGHT_ROLES)
        self.assertEqual(named_roles(reviewers), roles.REVIEW_ROLES)
        failed = section.split("- A child fails", 1)[1].split("\n- ", 1)[0]
        self.assertIn("When the failure carries a provider error, follow the next bullet before that respawn.", failed)
        self.assertLess(section.index("provider error"), section.index("roles.py backup"))

    def test_failure_handling_decides_completion_by_work_state(self):
        section = runtime_section("### Failure handling", "\n### ")
        self.assertNotIn("that child is still running nested work", section)
        for phrase in (
            "Decide completion by `workState` alone.",
            "it does not reopen the task",
            "0.0.46-nightly.20261008.2813",
            "startup recovery",
            "a turn held in a stopped queue does not count",
            "A stalled child",
        ):
            self.assertIn(phrase, section)
        step = runtime_section("5. Collect results.", "\n6. You own")
        self.assertIn("`hasPendingChildRuns` does not change that.", step)

    def test_local_state_reads_a_finished_result_after_restart(self):
        section = runtime_section("## Local state")
        self.assertIn("A task in `result_available` finished", section)
        self.assertIn("before you respawn its slice", section)


class OpenCodeLongCommandDocTest(unittest.TestCase):
    PARAGRAPH = (
        "Nobody resumes you after your turn ends, so a command left running in the background is lost.",
        "Run every long command in the foreground with a long enough timeout, for example a bash timeout of 600000 ms.",
        "If your shell moves a command to the background anyway, keep checking its output, "
        "with `sleep 60` between checks, until it finishes.",
        "Do not end your turn until your report is written.",
    )

    def test_delegation_step_3_carries_the_opencode_brief_paragraph(self):
        step = runtime_section("3. Spawn every independent child", "\n4. A child starts")
        cursor = "A Cursor harness sent `options` as a string, T3 refused the call, and the child then dropped the options."
        rule = step.split(cursor, 1)[1].split("\n   - ", 2)[1]
        self.assertTrue(rule.startswith("OpenCode moves a long command to the background, tells the model to end its turn"))
        self.assertNotIn("only OpenCode", rule)
        self.assertIn("T3 publishes the task's result when the first turn ends, and the later turn does not reopen the task.", rule)
        self.assertIn("Paste this paragraph unchanged into the brief of every child seated on OpenCode.", rule)
        self.assertIn("     > " + " ".join(self.PARAGRAPH) + "\n", rule)
        self.assertIn(
            "When an OpenCode child's task is terminal and the report file its brief named is missing, "
            "the task is not finished. Read its activity with `t3_thread_read`. "
            "While a later turn on its thread still runs, wait on it per step 5. "
            "Otherwise handle it per [Failure handling](#failure-handling).",
            rule,
        )

    def test_step_5_two_minute_rule_skips_a_background_wait(self):
        step = runtime_section("5. Collect results.", "\n6. You own")
        bullet = runtime_bullet(step, "   - A child with a final assistant message that holds the result")
        self.assertIn(
            "A message that says more work follows does not hold the result. "
            "A last message that says the child waits on a background command does not hold the result either, "
            "so this two-minute rule does not apply to it.",
            bullet,
        )

    def test_the_paragraph_is_stated_once(self):
        text = (ROOT / "t3/runtime.md").read_text()
        self.assertEqual(text.count("Nobody resumes you after your turn ends"), 1)


class SeatLaunchDocTest(unittest.TestCase):
    def setUp(self):
        self.runtime = (ROOT / "skills/pstack-runtime/SKILL.md").read_text()

    def test_mapping_sentence_renames_provider_instance_id_and_copies_options(self):
        section = self.runtime.split("## Top-level threads", 1)[1].split("\n## ", 1)[0]
        self.assertIn(
            "`modelSelection` is the seat with `providerInstanceId` renamed to `instanceId`, "
            "`model` copied, and `options` copied unchanged as the same object, "
            "including a boolean such as `{\"fastMode\": false}`.",
            section,
        )
        self.assertIn('"options": {"effort": "xhigh"}', section)
        self.assertIn("Confirm a launched thread per [Delegation](#delegation) step 3.", section)

    def test_readback_sentence_names_where_to_read_and_never_retries_without_options(self):
        step = self.runtime.split("3. Spawn every independent child", 1)[1].split("\n4. A child starts", 1)[0]
        self.assertIn(
            "After a `t3_thread_launch` or `delegate_task` call whose seat has `options`, "
            "read the applied options from the launch result's `modelSelection.options` or from "
            "`t3_thread_configuration` on the child's `childThreadId`, and never call again with the options removed.",
            step,
        )


class FastGrokDocTest(unittest.TestCase):
    def test_fast_grok_section_quotes_the_code_rule(self):
        section = runtime_section("### Excluded seats", "\n### ")
        self.assertIn(roles.EXCLUDED_RULE + ".", section)
        for phrase in (
            "`grok-4.7-build-fast`",
            "`grok-build` has no `fast` token",
            "A pickable model is one that is not excluded",
            '"fastMode": false',
            "No mode and no budget sets it to `true`.",
            "`validate` lists each one and exits 1.",
            '"seats": "catalog-required"',
            "Without a catalog, a role whose seats include `inherit`, and the `verifiers` default panel, "
            'report `"seats": "catalog-required"` when `--parent` names an excluded id.',
        ):
            self.assertIn(phrase, section)
        haiku = runtime_section("### Claude Haiku 5.5", "\n## ")
        self.assertIn(roles.HAIKU_BRIEF[0], haiku)
        self.assertIn(roles.HAIKU_BRIEF[1], haiku)

    def test_fast_grok_notes_match_roles_py(self):
        section = runtime_section("### Excluded seats", "\n### ")
        source = (ROOT / "t3/scripts/roles.py").read_text()
        for phrase in (
            "inherit replaced by",
            "inherit made explicit as",
            "so fastMode stays false",
            "skipped configured seat",
            "skipped inherit of",
            "refusing to write, even with --force",
        ):
            self.assertIn(phrase, section)
            self.assertIn(phrase, source)

    def test_no_source_sets_fast_mode_true(self):
        pattern = re.compile(r'"fastMode":\s*true')
        retired = (
            "sets `fastMode` only when",
            "Light mode never sets `fastMode`",
            "Add `fastMode` only when",
        )
        found = []
        for path in sorted((ROOT / "t3").rglob("*.md")):
            for number, line in enumerate(path.read_text().splitlines(), 1):
                if pattern.search(line) or any(phrase in line for phrase in retired):
                    found.append(f"{path.relative_to(ROOT)}:{number}")
        self.assertEqual(found, [])

    def test_roles_sites_say_pickable_not_first_listed(self):
        roles_text = runtime_section("## Roles")
        self.assertNotIn("first listed model", roles_text)
        fallback = runtime_section("### Fallback", "\n### ")
        self.assertIn(
            "Use the same provider's first pickable model. When it has none, `show` refuses the seat.",
            fallback,
        )
        for start, end in (
            ("### Built-in defaults", "\n### "),
            ("### Fallback", "\n### "),
            ("## Modes", "\n## "),
        ):
            self.assertIn("[Excluded seats](#excluded-seats)", runtime_section(start, end))

    def test_verifiers_skip_an_uninheritable_parent(self):
        defaults = runtime_section("### Built-in defaults", "### Excluded seats")
        self.assertIn('A thread on an excluded model gets no `"inherit"` seat', defaults)
        self.assertIn('`verifiers` is three `"inherit"` seats', defaults)

    def test_modes_never_set_fast_mode_true(self):
        section = runtime_section("### Resolve and carry the mode", "\n### ")
        self.assertIn("No mode sets `fastMode` to `true`.", section)


class SetupFastGrokDocTest(unittest.TestCase):
    def test_setup_never_writes_a_fast_grok_seat(self):
        text = (ROOT / "t3/setup.md").read_text()
        self.assertIn("Never write a fast Grok id such as `grok-4.7-build-fast`", text)
        self.assertIn("`write` refuses both, even with `--force`, and `validate` reports both.", text)
        self.assertIn("(../pstack-runtime/SKILL.md#excluded-seats)", text)
        self.assertNotIn("Add `fastMode` only when", text)


class AuthorSkillDocTest(unittest.TestCase):
    def test_seat_launching_test_goes_through_launches_seats(self):
        text = (ROOT / "t3/added/pstack-author-skill/SKILL.md").read_text()
        step = text.split("## 4. Test it on a fresh child", 1)[1].split("\n## 5. ", 1)[0]
        step2 = step.split("\n2. ", 1)[1].split("\n3. ", 1)[0]
        self.assertIn("stays on the `show` seat, unless its child launches seats.", step2)
        self.assertIn("`--launches-seats`", step2)
        self.assertIn("(../pstack-runtime/SKILL.md#claude-haiku-55)", step2)


class ForkDocTest(unittest.TestCase):
    def setUp(self):
        self.section = runtime_section("### Forks", "\n## ")

    def test_forks_live_under_top_level_threads(self):
        launch = runtime_section("## Top-level threads")
        self.assertIn("### Forks", launch)
        self.assertLess(launch.index("`create_threads` makes up to 20 threads"), launch.index("### Forks"))

    def test_a_fork_never_replaces_a_child(self):
        for sentence in (
            "Use them only for a separate thread this section allows.",
            "A fork never stands in for a child task, an Orchestrate sub-coordinator, or a fresh review round, "
            "and `task_status` does not apply to it.",
            "Fork only a read-only planner or investigation whose source context is the part it needs.",
            "Writers stay isolated per [Isolation](#isolation).",
        ):
            self.assertIn(sentence, self.section)

    def test_source_points_match_the_schema(self):
        self.assertIn(
            'Pass `sourcePoint` as `{"type": "latest_stable"}`, `{"type": "run", "runId": "<id>"}`, '
            'or `{"type": "checkpoint", "checkpointId": "<id>"}`.',
            self.section,
        )
        self.assertIn("Keep the returned `targetThreadId`.", self.section)

    def test_inherited_seat_is_checked_and_binding_is_read(self):
        for sentence in (
            "The fork inherits the source's configuration.",
            "Inheritance is not an exception.",
            "Read the fork with `t3_thread_read` for its `worktreePath`, `branch`, and `activeRunId` before you send anything.",
            "Treat a checkout it shares with another thread as read-only.",
        ):
            self.assertIn(sentence, self.section)
        self.assertIn("[Excluded seats](#excluded-seats)", self.section)

    def test_merge_back_is_authorized_and_read_back(self):
        for sentence in (
            "A one-line report stays the default.",
            "Call `t3_thread_merge_back` only when the user authorized it and the target needs the fork's reasoning, not only its result.",
            "A transfer moves context, not code, and it does not make a review independent.",
        ):
            self.assertIn(sentence, self.section)
        self.assertIn("`t3_thread_transfers`", self.section)

    def test_no_observed_behavior_is_a_guarantee(self):
        for claim in (
            "starts idle", "with no run", "runCount", "until the target's next turn consumes it",
            "It has the source's `worktreePath`", "stays `pending`",
        ):
            self.assertNotIn(claim, self.section)

    def test_orchestrate_sub_coordinator_stays_a_delegated_child(self):
        text = override_text("poteto-mode/playbooks/orchestrate.md")
        bullet = next(line for line in text.splitlines() if line.startswith("- **Sub-coordinator.**"))
        self.assertIn("A sub-coordinator is a `delegate_task` child that itself calls `delegate_task`.", bullet)
        self.assertNotIn("fork", bullet.lower())
        self.assertNotIn("#forks", text)


class ConfigureOwnerDocTest(unittest.TestCase):
    def setUp(self):
        launch = runtime_section("## Top-level threads", "\n### Forks")
        self.bullet = runtime_bullet(launch, "- Change an existing launched thread's model with `t3_thread_configure`")

    def test_configure_runs_only_from_a_playbook_step(self):
        self.assertIn("only when a playbook step already calls for that owner to run on another model", self.bullet)
        self.assertIn("Never call it because an owner keeps failing a gate.", self.bullet)

    def test_seat_comes_from_roles_and_is_read_back(self):
        for sentence in (
            "Resolve the seat per [Roles](#roles) with `roles.py show`.",
            "Call it when `t3_thread_read` shows no `activeRunId`, or after `t3_thread_interrupt` and `t3_thread_wait` end the run.",
            "compare `instanceId`, `model`, and every option per [Delegation](#delegation) step 3.",
            "On a refusal or a mismatch, send nothing to the thread and report the tool's error text.",
        ):
            self.assertIn(sentence, self.bullet)

    def test_configure_always_passes_a_concrete_seat(self):
        for sentence in (
            "`t3_thread_configure` requires a concrete `modelSelection`, so always pass one, even for an `inherit` seat.",
            "Build it from the resolved seat with `providerInstanceId` renamed to `instanceId`, `model` copied, and `options` copied unchanged.",
            "When the resolved seat is `inherit`, use this thread's own provider and model, `inheritedProviderInstanceId` and "
            "`inheritedModel` from `orchestrator_capabilities`, as the concrete seat when it passes [Excluded seats](#excluded-seats).",
            "When it fails that check, do not configure the thread, and report that no replacement seat could be selected.",
        ):
            self.assertIn(sentence, self.bullet)
        for claim in ("built per the `modelSelection` bullet above", "Omit `modelSelection`"):
            self.assertNotIn(claim, self.bullet)

    def test_configure_keeps_gates_and_fresh_protocols(self):
        for sentence in (
            "The call does not change the thread's permission modes, and it keeps the thread's retry count, scope, standing orders, and gates.",
            "The thread keeps its history, so it never counts as a fresh worker or a fresh reviewer.",
            "Never configure a verifier or reviewer thread.",
            "A failed child task gets a fresh child per [Failure handling](#failure-handling).",
            "A send-back and a usage-limit relaunch get the fresh worker their playbook or `roles.py backup` names.",
            "None of them uses `t3_thread_configure`.",
        ):
            self.assertIn(sentence, self.bullet)

    def test_no_in_flight_switch_or_escalation_claim(self):
        for claim in ("escalate an owner", "The next turn runs on the new seat", "instead of relaunching it"):
            self.assertNotIn(claim, self.bullet)

    def test_orchestrate_retry_links_configure_for_owners_only(self):
        text = override_text("poteto-mode/playbooks/orchestrate.md")
        bullet = next(line for line in text.splitlines() if line.startswith("- Retry by mode:"))
        self.assertIn(
            "A long-lived owner takes the new model in place per "
            "[Top-level threads](../../pstack-runtime/SKILL.md#top-level-threads), and a child gets a fresh child on it.",
            bullet,
        )
        self.assertIn("Two retries, then abandon the unit and replan around it.", bullet)


class PromoteQueuedCorrectionDocTest(unittest.TestCase):
    def setUp(self):
        self.launch = runtime_section("## Top-level threads", "\n### Forks")
        self.bullet = runtime_bullet(self.launch, "- A correction you queued earlier")

    def test_promote_sits_directly_under_the_auto_report_rule(self):
        lines = self.launch.splitlines()
        report = next(i for i, line in enumerate(lines) if line.startswith("- Autopilot-full, Autopilot-stack, and Orchestrate owners"))
        self.assertTrue(lines[report + 1].startswith("- A correction you queued earlier"))

    def test_promote_names_the_tool_keys_and_reads_delivery(self):
        for sentence in (
            "call `t3_queue_list` on the recipient and find the `queuedRunId` of that exact message.",
            "Read the recipient's `activeRunId` with `t3_thread_read`.",
            "Call `t3_queue_promote_to_steer` with that `queuedRunId`, the `activeRunId` as `targetRunId`, and the recipient's `threadId`.",
            "Its `sequence` result means T3 accepted the call, not that the run received the message.",
            "Until that read shows it, the delivery is unresolved.",
            "A `cancelled` queued run alone proves nothing.",
            "never resend a correction that may already be delivered.",
        ):
            self.assertIn(sentence, self.bullet)

    def test_brigade_events_are_never_promoted(self):
        self.assertIn(
            "Never promote brigade's event lines to an executive admin, a digest message, or a message that needs a turn of its own.",
            self.bullet,
        )
        self.assertIn("Brigade's event lines to an executive admin stay on `mode: \"queue\"`", self.launch)

    def test_cancellation_is_not_success(self):
        self.assertNotIn("a wait on that run is not a failure", self.bullet)
        self.assertNotIn("then reports `cancelled`", self.bullet)


class RunScheduleNowDocTest(unittest.TestCase):
    def setUp(self):
        self.bullet = runtime_bullet(runtime_section("## Scheduling"), "- To run an enabled `interval` schedule's work now")

    def test_run_now_takes_the_scheduled_task_id(self):
        self.assertIn("call `run_scheduled_task_now` with its ID as `taskId`.", self.bullet)
        self.assertIn("from `scheduledTaskId` in `list_scheduled_tasks`", self.bullet)

    def test_run_now_is_dispatch_not_completion(self):
        for sentence in (
            "Each call is a new manual run.",
            "Before you retry a lost or failed response, read `list_scheduled_tasks` and the bound thread with `t3_thread_read`.",
            "The result means T3 dispatched the run, not that its turn finished.",
            "Report the returned `nextRunAt` as T3 returned it.",
        ):
            self.assertIn(sentence, self.bullet)

    def test_run_now_keeps_pause_and_watch_rules(self):
        for sentence in (
            "No event calls it by rule, a merge or an answer included.",
            "Never run a paused schedule before the answer permits work.",
            "Never run one to wait on a child, to wait on a pull request's checks, reviews, or conflicts, "
            "or to repeat a `watch_pull_request` wake.",
            "It requires a full-access or default caller.",
        ):
            self.assertIn(sentence, self.bullet)

    def test_run_now_promises_no_cadence_and_grants_no_work(self):
        self.assertNotIn("counts from it", self.bullet)
        self.assertNotIn("do the tick's work in this turn", self.bullet)
        self.assertIn("only when this thread owns that work and its mode allows the edits", self.bullet)


class VisualReportsDocTest(unittest.TestCase):
    def setUp(self):
        self.section = runtime_section("## Visual reports")

    def test_section_sits_after_verification_surfaces(self):
        text = (ROOT / "t3/runtime.md").read_text()
        self.assertLess(text.index("## Verification surfaces"), text.index("## Visual reports"))
        self.assertLess(text.index("## Visual reports"), text.index("## History"))
        bullet = next(line for line in text.splitlines() if line.startswith("- Web or Electron UI:"))
        self.assertNotIn("html_", bullet)

    def test_vocabulary_row_points_at_the_section(self):
        text = (ROOT / "t3/runtime.md").read_text()
        row = next(line for line in text.splitlines() if line.startswith("| status page, dashboard, report table, chart |"))
        self.assertIn("`html_preview`, then `html_render`, inside a reply already due", row)
        self.assertIn("[Visual reports](#visual-reports)", row)

    def test_page_only_rides_a_reply_already_due(self):
        for sentence in (
            "A page is for a reply that is already due.",
            "A short status with no table stays text.",
            "A rendered page is a reply the user reads, even with no reply text.",
            "Render none on a wake that sends no reply.",
            "Brigade at `digest` renders no page, so its replies stay in the plain form "
            "[Digest messages](../brigade/SKILL.md#digest-messages) sets.",
        ):
            self.assertIn(sentence, self.section)

    def test_preview_render_and_text_fallback(self):
        for sentence in (
            "Call `html_preview` with it. Fix every console error and every clipped or overlapping element.",
            "Call `html_render` with the document, a `title`, and the preview's `contentHeight` as `height`, raised to 80 or capped at 2000.",
            "Every decision that waits on the user, every PR link, and the store and report paths stay in the reply text",
            "Leave `html`, `body`, and the outermost element with no background color",
            "When either tool is missing or `html_render` fails, send the same facts as text.",
        ):
            self.assertIn(sentence, self.section)

    def test_orchestrate_reply_keeps_upstream_facts_and_links_the_section(self):
        text = override_text("poteto-mode/playbooks/orchestrate.md")
        reply = next(line for line in text.splitlines() if line.startswith("**Reply:**"))
        self.assertTrue(reply.startswith(
            "**Reply:** at checkpoints and close: the predicate and the count against it from `units.tsv` and `ledger.tsv`, "
            "tracks and what each landed, the frontier (PR list plus SHAs), verdicts summary, what was abandoned and why, "
            "gates awaiting the human (the only asks), the store path, and the trail path. "
            "Numbers from the tables, not narrative. Include PR links."
        ))
        self.assertIn("per [Visual reports](../../pstack-runtime/SKILL.md#visual-reports).", reply)
        self.assertIn("The gates, PR links, store path, and trail path stay in the reply text.", reply)


class NoCommentsReadOnlyDocTest(unittest.TestCase):
    def setUp(self):
        self.text = override_text("no-comments/SKILL.md")
        self.scope = self.text.split("## Scope", 1)[1].split("\n## Steps", 1)[0]

    def test_read_only_caller_never_runs_the_skill(self):
        for sentence in (
            "This skill edits files and delegates edits.",
            "A caller working under a read-only instruction never runs it and spawns no Comment Sicko, whatever its role label.",
            "per [the runtime's Permissions section](../pstack-runtime/SKILL.md#permissions).",
            "Step 1's `role: \"review\"` is a label and does not make Comment Sicko read-only.",
        ):
            self.assertIn(sentence, self.scope)

    def test_guard_leads_the_scope_and_keeps_the_pointer_once(self):
        self.assertLess(self.scope.index("This skill edits files"), self.scope.index("Use the caller's files or diff."))
        self.assertEqual(self.text.count(pointer_sentence("skill")), 1)

    def test_authorized_writing_flow_is_unchanged(self):
        self.assertIn('Spawn Comment Sicko as a fresh child with `delegate_task` (`role: "review"`', self.text)
        self.assertIn("It edits comments in the shared checkout, so run it alone", self.text)
        self.assertNotIn("readonly", self.scope)


class BrigadeAdminSplitDocTest(unittest.TestCase):
    def setUp(self):
        self.brigade = (ROOT / "skills/brigade/SKILL.md").read_text()
        self.admin = (ROOT / "skills/brigade-admin/SKILL.md").read_text()

    @staticmethod
    def headings(text, prefix="#"):
        return [line for line in unfenced_lines(text) if line.startswith(prefix)]

    @classmethod
    def slugs(cls, text):
        return {heading_slug(line.lstrip("#").strip()) for line in cls.headings(text)}

    def test_admin_headings_are_in_brigade_admin_and_not_in_brigade(self):
        admin = self.headings(self.admin, "## ")
        brigade = [line.lstrip("#").strip() for line in self.headings(self.brigade)]
        for heading in (
            "Open an executive admin",
            "Admin first service",
            "Admin service",
            "Admin messages",
            "Rulings",
            "What the admin never does",
            "Admin recovery and retirement",
            "What the user hears from the admin",
        ):
            with self.subTest(heading=heading):
                self.assertIn(f"## {heading}", admin)
                self.assertNotIn(heading, brigade)

    def test_no_line_of_40_characters_is_in_both_skills_but_the_runtime_pointer_and_the_pin_step(self):
        def long_lines(text):
            return {line for line in text.splitlines() if len(line) >= 40}

        self.assertEqual(
            long_lines(self.brigade) & long_lines(self.admin),
            {
                "Read [the pstack-t3 runtime](../pstack-runtime/SKILL.md) before spawning workers, "
                "choosing models, scheduling, or isolating work. It maps those steps onto T3's orchestrator tools.",
                '1. `t3_thread_organize` with `action: "pin"` and no `threadId`.',
            },
        )

    def test_reporting_section_links_brigade_admin(self):
        section = self.brigade.split("\n## Reporting to an executive admin\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("(../brigade-admin/SKILL.md)", section)

    def test_links_between_the_two_skills_and_in_file_links_in_both_name_a_heading(self):
        cross = re.findall(r"\(\.\./brigade/SKILL\.md#([^)\s]+)\)", self.admin)
        self.assertIn("reporting-to-an-executive-admin", cross)
        self.assertEqual([fragment for fragment in cross if fragment not in self.slugs(self.brigade)], [])
        back = re.findall(r"\(\.\./brigade-admin/SKILL\.md#([^)\s]+)\)", self.brigade)
        self.assertIn("rulings", back)
        self.assertEqual([fragment for fragment in back if fragment not in self.slugs(self.admin)], [])
        for name, text in (("brigade", self.brigade), ("brigade-admin", self.admin)):
            with self.subTest(skill=name):
                own = re.findall(r"\]\(#([^)\s]+)\)", text)
                self.assertIn("filing-tracker-work" if name == "brigade" else "rulings", own)
                self.assertEqual([fragment for fragment in own if fragment not in self.slugs(text)], [])

    def test_a_section_of_the_other_skill_is_named_only_as_a_link(self):
        # "Terms", "The script", and "Run a service" also occur as plain words, so they are only required once.
        for section in ("Terms", "The script", "Run a service"):
            with self.subTest(section=section):
                self.assertIn(f"[{section}](../brigade/SKILL.md#{heading_slug(section)})", self.admin)
        for text, target, sections in (
            (
                self.admin,
                "../brigade/SKILL.md",
                (
                    "Open a restaurant",
                    "First service",
                    "Liveness check",
                    "Git and PR housekeeping",
                    "Filing tracker work",
                    "Digest messages",
                    "Reporting to an executive admin",
                ),
            ),
            (
                self.brigade,
                "../brigade-admin/SKILL.md",
                ("Admin service", "Admin messages", "Rulings", "What the admin never does"),
            ),
        ):
            for section in sections:
                with self.subTest(section=section):
                    link = f"[{section}]({target}#{heading_slug(section)})"
                    self.assertGreater(text.count(link), 0)
                    self.assertEqual(text.count(section), text.count(link))

    def test_a_rule_the_coordinator_and_the_admin_share_is_stated_in_one_skill(self):
        skills = {"brigade": self.brigade, "brigade-admin": self.admin}
        for phrase, owner in (
            ("`failed`, `drained`, `report`, `reply`, `contest`, and `appeal`", "brigade"),
            ('with `t3_thread_send` and mode `"queue"`', "brigade"),
            ("until an entry of the first holder lands", "brigade"),
            ("starts no new work on those paths", "brigade"),
            ("it holds and sends `appeal`", "brigade"),
            ("refuses to drop a source while a `waiting` or `assigned` ticket came from it", "brigade"),
            ("The ref stays unchanged through every `ticket move`", "brigade"),
            ("The check runs under the store lock", "brigade"),
            ("A message-only line never appears in `sync`", "brigade-admin"),
            ("Every other holder's claim on those paths is refused", "brigade-admin"),
            ("Direct a coordinator's own work", "brigade-admin"),
            ("An item the other depends on, as a `contest` line stated, lands first", "brigade-admin"),
            ("when no contest covers the two holders", "brigade-admin"),
            ("`ticket <restaurant>: run ticket take`", "brigade"),
            ("`from-user <restaurant>: <the user's words>`", "brigade"),
            ("`answer <restaurant> Q<n>: <answer>`", "brigade"),
            ("`reports-to <restaurant> <thread>`", "brigade"),
            ("`ruling <restaurant> R<n>: <decision>`", "brigade"),
            ("`$B status` prints `thread <id>` first and `owner <thread>@<generation>` last", "brigade"),
            ("End the message with one line that names that path", "brigade"),
        ):
            with self.subTest(phrase=phrase):
                self.assertEqual([name for name, text in skills.items() if phrase in text], [owner])
        for phrase in (
            "`sync` never prints them",
            "The admin's `sync` relays",
            "It never directs this restaurant's own work",
            "and the admin escalates",
            "The admin then rules `dependency`",
            "A reservation on the paths refuses",
            "The admin publishes each request",
        ):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, self.brigade)
        for phrase in (
            "The message-only lines, ",
            'with mode `"queue"`',
            "`land` then holds the other holder's entries",
            "keeps the holder from starting new work",
            "the coordinator holds and has not complied",
            "A ruling binds the coordinators",
            "That is refused while it still has waiting or assigned tickets",
            "`ticket move` in step 4 keeps that ref",
            "Every `brigade.py` write checks the owner token under the store lock",
            "The coordinator's store decides whether",
            "no store row keeps it",
            "It prints `thread <id>` first",
            "asks the holder to move it",
            "End with one line naming the full update",
        ):
            with self.subTest(phrase=phrase):
                self.assertNotIn(phrase, self.admin)

    def test_admin_names_each_request_line_and_links_brigade_for_its_text(self):
        # Any placeholder counts, so a line written with `<coordinator>` is still a second copy of the format.
        self.assertEqual(re.findall(r"`(?:ticket|from-user|answer|reports-to|ruling) <[^`]*`", self.admin), [])
        messages = self.admin.split("\n## Admin messages\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn(
            "The exact text of each line is in [Reporting to an executive admin]"
            "(../brigade/SKILL.md#reporting-to-an-executive-admin), under Requests.",
            messages,
        )
        self.assertIn(
            "This skill's `<coordinator>`, the directory name of the coordinator the line goes to, "
            "fills the `<restaurant>` field.",
            messages,
        )
        rows = [line.split(" | ", 1)[0] for line in messages.splitlines() if line.startswith("| `")]
        self.assertEqual(rows, ["| `ticket`", "| `from-user`", "| `answer`", "| `reports-to`", "| `ruling`"])
        requests = self.brigade.split("\n**Requests.**", 1)[1].split("\n**A ruling's side.**", 1)[0]
        for line in (
            "ticket <restaurant>: run ticket take",
            "from-user <restaurant>: <the user's words>",
            "answer <restaurant> Q<n>: <answer>",
            "reports-to <restaurant> <thread>",
            "ruling <restaurant> R<n>: <decision>",
        ):
            with self.subTest(line=line):
                self.assertEqual(requests.count(f"`{line}`"), 1)

    def test_admin_links_brigades_script_and_ships_none(self):
        self.assertIn("(../brigade/scripts/brigade.py)", self.admin)
        self.assertTrue((ROOT / "skills/brigade/scripts/brigade.py").is_file())
        self.assertFalse((ROOT / "skills/brigade-admin/scripts").exists())

    def test_brigade_description_sends_the_admin_trigger_to_brigade_admin(self):
        description = next(line for line in self.brigade.splitlines() if line.startswith("description:"))
        self.assertIn(
            "For an executive admin over the coordinators on one repository, use brigade-admin.", description
        )
        self.assertNotIn("an executive admin over the coordinators on one repository'", description)

    def test_neither_description_has_a_mid_sentence_colon(self):
        for name, text in (("brigade", self.brigade), ("brigade-admin", self.admin)):
            with self.subTest(skill=name):
                description = next(line for line in text.splitlines() if line.startswith("description:"))
                self.assertNotIn(": ", description.removeprefix("description: "))
                self.assertIn(". Use for '", description)

    def test_catalog_lists_brigade_admin_under_plan_and_run_long_work(self):
        import catalog
        group = catalog.render(ROOT / "skills").split("\n## Plan and run long work\n", 1)[1].split("\n## ", 1)[0]
        self.assertIn("| [`brigade-admin`](../skills/brigade-admin/SKILL.md) |", group)


if __name__ == "__main__":
    unittest.main()
