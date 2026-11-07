from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unicodedata
import unittest
from pathlib import Path

from evaluations.content_quality_gate import (
    DIMENSIONS,
    EMPTY_WORKSPACE_SHA256,
    GateError,
    _report_template,
    corpus_bundle_sha256,
    evaluate,
    git_source_bundle_sha256,
    render_generation_prompt,
    render_judge_prompt,
    working_source_bundle_sha256,
)


GENRES = [
    "romance",
    "comedy",
    "workplace",
    "family",
    "suspense",
    "revenge",
    "rural",
    "fantasy",
    "historical",
    "sports",
    "slice-of-life",
    "science-fiction",
]
NEGATIVE_CONTROLS = {1, 6, 10}
MECHANISM_CASES = {
    "consequential_choice": {0, 4, 8},
    "contested_evidence": {2, 5, 9},
    "literal_precise_deadline": {3, 7, 11},
}
REPLICATE_COUNT = 3
GENERATION_TEMPLATE = "Read the Skill.\n\n{{CASE_SPEC}}\n\nReturn only the screenplay.\n"
JUDGE_TEMPLATE = (
    "{{RUBRIC}}\n\n{{CASE_SPEC}}\n\nA\n{{ARTIFACT_A}}\n\n"
    "B\n{{ARTIFACT_B}}\n\n{{REPORT_TEMPLATE}}\n"
)
RUBRIC = "Score both works on the declared dimensions.\n"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def distributed_score(total: int) -> dict[str, int]:
    remaining = total
    result: dict[str, int] = {}
    for dimension, maximum in DIMENSIONS.items():
        score = min(maximum, remaining)
        result[dimension] = score
        remaining -= score
    if remaining:
        raise ValueError("score exceeds rubric maximum")
    return result


class ContentQualityGateTests(unittest.TestCase):
    def build_workspace(
        self,
        root: Path,
        *,
        baseline_total: int = 70,
        candidate_total: int = 75,
        candidate_leak_case: int | None = None,
    ) -> dict[str, Path]:
        repo = root / "repo"
        run = root / "run"
        evaluations = repo / "evaluations"
        cases_dir = evaluations / "content-quality-cases"
        writer = repo / "skills/short-drama-write/SKILL.md"
        reviewer = repo / "skills/short-drama-review/rubric.md"
        writer.parent.mkdir(parents=True)
        reviewer.parent.mkdir(parents=True)
        cases_dir.mkdir(parents=True)
        run.mkdir(parents=True)
        writer.write_text("baseline writer guidance\n", encoding="utf-8")
        reviewer.write_text("review guidance\n", encoding="utf-8")

        config = {
            "schema_version": 3,
            "generation_replicates": REPLICATE_COUNT,
            "generation_workspace_policy": "source-bundle-only",
            "judge_workspace_policy": "prompt-only",
            "generator": {
                "cli": "codex",
                "model": "generator-model",
                "reasoning_effort": "high",
                "session_policy": "fresh",
            },
            "judges": {
                "codex": {
                    "cli": "codex",
                    "model": "codex-judge",
                    "reasoning_effort": "high",
                    "session_policy": "fresh",
                },
                "kimi": {
                    "cli": "kimi",
                    "model": "kimi-code/k3",
                    "reasoning_effort": "provider-default",
                    "session_policy": "fresh",
                },
            },
        }
        config_path = evaluations / "content-quality-config.json"
        generation_template_path = evaluations / "content-quality-generation-prompt.md"
        judge_template_path = evaluations / "content-quality-judge-prompt.md"
        rubric_path = evaluations / "content-quality-rubric.md"
        write_json(config_path, config)
        generation_template_path.write_text(GENERATION_TEMPLATE, encoding="utf-8")
        judge_template_path.write_text(JUDGE_TEMPLATE, encoding="utf-8")
        rubric_path.write_text(RUBRIC, encoding="utf-8")

        corpus_cases = []
        for index, genre in enumerate(GENRES):
            case_id = f"case-{index + 1}"
            spec = cases_dir / f"{case_id}.md"
            spec.write_text(
                f"# Brief {index + 1}\n\nDistinct premise {index + 1}.\n",
                encoding="utf-8",
            )
            corpus_cases.append(
                {
                    "case_id": case_id,
                    "split": "development" if index < 8 else "holdout",
                    "genre": genre,
                    "negative_control": index in NEGATIVE_CONTROLS,
                    "mechanisms": {
                        mechanism: index in enabled_cases
                        for mechanism, enabled_cases in MECHANISM_CASES.items()
                    },
                    "case_spec": f"content-quality-cases/{case_id}.md",
                }
            )
        corpus = {
            "schema_version": 3,
            "corpus_id": "test-cross-genre-v3",
            "holdout_policy": {
                "development": "reusable",
                "holdout": "single-use after freeze",
            },
            "cases": corpus_cases,
        }
        corpus_path = evaluations / "content-quality-corpus.json"
        write_json(corpus_path, corpus)

        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(
            ["git", "config", "user.email", "gate-tests@example.invalid"],
            cwd=repo,
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Gate Tests"],
            cwd=repo,
            check=True,
        )
        subprocess.run(["git", "add", "."], cwd=repo, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "baseline"],
            cwd=repo,
            check=True,
        )
        baseline_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        writer.write_text("candidate writer guidance\n", encoding="utf-8")

        leakage_terms = root / "trusted-leakage-terms.txt"
        leakage_terms.write_text(
            "\n".join(f"sealed-private-token-{index}" for index in range(8)) + "\n",
            encoding="utf-8",
        )
        baseline_bundle = git_source_bundle_sha256(repo, baseline_commit)
        candidate_bundle = working_source_bundle_sha256(repo)
        provenance = {
            "baseline_commit": baseline_commit,
            "baseline_skill_bundle_sha256": baseline_bundle,
            "candidate_skill_bundle_sha256": candidate_bundle,
            "corpus_bundle_sha256": corpus_bundle_sha256(corpus_path),
            "corpus_sha256": digest(corpus_path),
            "evaluation_config_sha256": digest(config_path),
            "gate_sha256": digest(
                Path(__file__).resolve().parents[1]
                / "evaluations/content_quality_gate.py"
            ),
            "generation_prompt_template_sha256": digest(generation_template_path),
            "judge_prompt_template_sha256": digest(judge_template_path),
            "rubric_sha256": digest(rubric_path),
            "leakage_terms_sha256": digest(leakage_terms),
        }
        seal = {"seal_id": "sealed-test-round", **provenance}
        trusted_seal = root / "trusted-seal.json"
        write_json(trusted_seal, {"schema_version": 1, "holdout_seal": seal})

        manifest_cases = []
        for index, registry_case in enumerate(corpus_cases):
            case_id = registry_case["case_id"]
            copied_spec = run / "cases" / f"{case_id}.md"
            copied_spec.parent.mkdir(parents=True, exist_ok=True)
            source_spec = evaluations / registry_case["case_spec"]
            copied_spec.write_bytes(source_spec.read_bytes())
            generation_prompt = run / "prompts/generation" / f"{case_id}.md"
            generation_prompt.parent.mkdir(parents=True, exist_ok=True)
            generation_prompt.write_text(
                render_generation_prompt(
                    GENERATION_TEMPLATE,
                    copied_spec.read_text(encoding="utf-8"),
                ),
                encoding="utf-8",
            )

            replicate_entries = []
            for replicate_index in range(1, REPLICATE_COUNT + 1):
                replicate_id = f"r{replicate_index:02d}"
                baseline = run / "baseline" / case_id / f"{replicate_id}.md"
                candidate = run / "candidate" / case_id / f"{replicate_id}.md"
                baseline.parent.mkdir(parents=True, exist_ok=True)
                candidate.parent.mkdir(parents=True, exist_ok=True)
                baseline.write_text(
                    f"# Baseline {index} {replicate_id}\n\nCafé baseline work {index} {replicate_id}.\n",
                    encoding="utf-8",
                )
                candidate_text = (
                    f"# Candidate {index} {replicate_id}\n\n"
                    f"Candidate work {index} {replicate_id}.\n"
                )
                if candidate_leak_case == index and replicate_index == 1:
                    candidate_text += "sealed-private-token-0\n"
                candidate.write_text(candidate_text, encoding="utf-8")

                generation_runs = {}
                for arm, artifact, source_bundle in (
                    ("baseline", baseline, baseline_bundle),
                    ("candidate", candidate, candidate_bundle),
                ):
                    run_id = f"{case_id}-{replicate_id}-{arm}-generation"
                    receipt = run / "receipts/generation" / f"{run_id}.json"
                    write_json(
                        receipt,
                        {
                            "schema_version": 2,
                            "run_id": run_id,
                            "case_id": case_id,
                            "replicate_id": replicate_id,
                            "arm": arm,
                            "model_config": config["generator"],
                            "prompt_sha256": digest(generation_prompt),
                            "artifact_sha256": digest(artifact),
                            "source_bundle_sha256": source_bundle,
                            "workspace_policy": config[
                                "generation_workspace_policy"
                            ],
                            "workspace_bundle_sha256": source_bundle,
                            "cli_version": "test-generator 1",
                        },
                    )
                    generation_runs[arm] = {
                        "run_id": run_id,
                        "receipt": receipt.relative_to(run).as_posix(),
                        "receipt_sha256": digest(receipt),
                    }

                judge_runs = []
                for family in ("codex", "kimi"):
                    for baseline_label in ("A", "B"):
                        candidate_label = "B" if baseline_label == "A" else "A"
                        artifacts = {
                            baseline_label: digest(baseline),
                            candidate_label: digest(candidate),
                        }
                        artifact_paths = {
                            baseline_label: baseline,
                            candidate_label: candidate,
                        }
                        judge_id = (
                            f"{case_id}-{replicate_id}-{family}-"
                            f"baseline-{baseline_label.lower()}"
                        )
                        report_template = _report_template(
                            case_id,
                            replicate_id,
                            judge_id,
                            family,
                            digest(copied_spec),
                            artifacts,
                        )
                        prompt = run / "prompts/judges" / f"{judge_id}.md"
                        prompt.parent.mkdir(parents=True, exist_ok=True)
                        prompt.write_text(
                            render_judge_prompt(
                                JUDGE_TEMPLATE,
                                RUBRIC,
                                copied_spec.read_text(encoding="utf-8"),
                                artifact_paths["A"].read_text(encoding="utf-8"),
                                artifact_paths["B"].read_text(encoding="utf-8"),
                                report_template,
                            ),
                            encoding="utf-8",
                        )
                        report = run / "reports" / family / f"{judge_id}.json"
                        result = report_template
                        result["scores"][baseline_label] = distributed_score(
                            baseline_total
                        )
                        result["scores"][candidate_label] = distributed_score(
                            candidate_total
                        )
                        result["preference"] = candidate_label
                        write_json(report, result)
                        receipt = run / "receipts/judges" / f"{judge_id}.json"
                        write_json(
                            receipt,
                            {
                                "schema_version": 2,
                                "run_id": judge_id,
                                "case_id": case_id,
                                "replicate_id": replicate_id,
                                "judge_id": judge_id,
                                "family": family,
                                "model_config": config["judges"][family],
                                "prompt_sha256": digest(prompt),
                                "report_sha256": digest(report),
                                "workspace_policy": config[
                                    "judge_workspace_policy"
                                ],
                                "workspace_bundle_sha256": EMPTY_WORKSPACE_SHA256,
                                "cli_version": f"test-{family} 1",
                            },
                        )
                        judge_runs.append(
                            {
                                "judge_id": judge_id,
                                "family": family,
                                "baseline_label": baseline_label,
                                "prompt": prompt.relative_to(run).as_posix(),
                                "prompt_sha256": digest(prompt),
                                "report": report.relative_to(run).as_posix(),
                                "report_sha256": digest(report),
                                "receipt": receipt.relative_to(run).as_posix(),
                                "receipt_sha256": digest(receipt),
                            }
                        )

                replicate_entries.append(
                    {
                        "replicate_id": replicate_id,
                        "baseline_artifact": baseline.relative_to(run).as_posix(),
                        "baseline_sha256": digest(baseline),
                        "candidate_artifact": candidate.relative_to(run).as_posix(),
                        "candidate_sha256": digest(candidate),
                        "generation_runs": generation_runs,
                        "judge_runs": judge_runs,
                    }
                )

            manifest_cases.append(
                {
                    **registry_case,
                    "case_spec": copied_spec.relative_to(run).as_posix(),
                    "case_spec_sha256": digest(copied_spec),
                    "generation_prompt": generation_prompt.relative_to(run).as_posix(),
                    "generation_prompt_sha256": digest(generation_prompt),
                    "replicates": replicate_entries,
                }
            )

        manifest = run / "manifest.json"
        write_json(
            manifest,
            {
                "schema_version": 5,
                "corpus_id": corpus["corpus_id"],
                "provenance": provenance,
                "holdout_seal": seal,
                "cases": manifest_cases,
            },
        )
        return {
            "repo": repo,
            "run": run,
            "manifest": manifest,
            "corpus": corpus_path,
            "config": config_path,
            "leakage_terms": leakage_terms,
            "trusted_seal": trusted_seal,
            "writer": writer,
            "reviewer": reviewer,
        }

    def evaluate_workspace(self, workspace: dict[str, Path]) -> dict:
        return evaluate(
            workspace["manifest"],
            leakage_terms_path=workspace["leakage_terms"],
            trusted_seal_path=workspace["trusted_seal"],
            repo_root=workspace["repo"],
            corpus_path=workspace["corpus"],
            config_path=workspace["config"],
        )

    def load_manifest(self, workspace: dict[str, Path]) -> dict:
        return json.loads(workspace["manifest"].read_text(encoding="utf-8"))

    def save_manifest(self, workspace: dict[str, Path], manifest: dict) -> None:
        write_json(workspace["manifest"], manifest)

    def mutate_report(
        self,
        workspace: dict[str, Path],
        case_index: int,
        replicate_index: int,
        run_index: int,
        mutate,
    ) -> None:
        manifest = self.load_manifest(workspace)
        run_entry = manifest["cases"][case_index]["replicates"][replicate_index][
            "judge_runs"
        ][run_index]
        report_path = workspace["run"] / run_entry["report"]
        report = json.loads(report_path.read_text(encoding="utf-8"))
        mutate(report, run_entry)
        write_json(report_path, report)
        run_entry["report_sha256"] = digest(report_path)
        receipt_path = workspace["run"] / run_entry["receipt"]
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["report_sha256"] = digest(report_path)
        write_json(receipt_path, receipt)
        run_entry["receipt_sha256"] = digest(receipt_path)
        self.save_manifest(workspace, manifest)

    def test_bound_multi_replicate_evidence_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            result = self.evaluate_workspace(workspace)
        self.assertTrue(result["passed"])
        self.assertEqual(result["case_count"], 12)
        self.assertEqual(result["generation_replicates"], REPLICATE_COUNT)
        self.assertEqual(result["genre_count"], 12)
        self.assertEqual(result["negative_control_count"], 3)
        self.assertEqual(result["baseline_macro_mean"], 70.0)
        self.assertEqual(result["candidate_macro_mean"], 75.0)

    def test_manifest_cannot_relabel_trusted_case_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            manifest = self.load_manifest(workspace)
            manifest["cases"][0]["genre"] = "invented-genre"
            self.save_manifest(workspace, manifest)
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_manifest_must_include_every_corpus_case(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            manifest = self.load_manifest(workspace)
            manifest["cases"] = manifest["cases"][:-1]
            self.save_manifest(workspace, manifest)
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_missing_replicate_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            manifest = self.load_manifest(workspace)
            manifest["cases"][0]["replicates"].pop()
            self.save_manifest(workspace, manifest)
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_duplicate_replicate_identity_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            manifest = self.load_manifest(workspace)
            manifest["cases"][0]["replicates"][2]["replicate_id"] = "r02"
            self.save_manifest(workspace, manifest)
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_cross_replicate_artifact_reuse_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            manifest = self.load_manifest(workspace)
            first = manifest["cases"][0]["replicates"][0]
            second = manifest["cases"][0]["replicates"][1]
            second["baseline_artifact"] = first["baseline_artifact"]
            second["baseline_sha256"] = first["baseline_sha256"]
            self.save_manifest(workspace, manifest)
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_whitespace_and_unicode_only_replicate_clone_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            manifest = self.load_manifest(workspace)
            first = manifest["cases"][0]["replicates"][0]
            second = manifest["cases"][0]["replicates"][1]
            first_path = workspace["run"] / first["baseline_artifact"]
            second_path = workspace["run"] / second["baseline_artifact"]
            clone = unicodedata.normalize(
                "NFD", first_path.read_text(encoding="utf-8")
            ).replace("\n", "\r\n")
            second_path.write_bytes((clone.rstrip() + "   \r\n\r\n").encode("utf-8"))
            self.assertNotEqual(digest(first_path), digest(second_path))
            second["baseline_sha256"] = digest(second_path)
            self.save_manifest(workspace, manifest)
            with self.assertRaisesRegex(GateError, "content-distinct"):
                self.evaluate_workspace(workspace)

    def test_candidate_source_change_invalidates_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            workspace["writer"].write_text(
                "later candidate guidance\n", encoding="utf-8"
            )
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_generation_receipt_rejects_full_worktree_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            manifest = self.load_manifest(workspace)
            generation_run = manifest["cases"][0]["replicates"][0][
                "generation_runs"
            ]["baseline"]
            receipt_path = workspace["run"] / generation_run["receipt"]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["workspace_policy"] = "full-worktree"
            write_json(receipt_path, receipt)
            generation_run["receipt_sha256"] = digest(receipt_path)
            self.save_manifest(workspace, manifest)
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_judge_receipt_rejects_nonempty_workspace_policy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            manifest = self.load_manifest(workspace)
            judge_run = manifest["cases"][0]["replicates"][0]["judge_runs"][0]
            receipt_path = workspace["run"] / judge_run["receipt"]
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            receipt["workspace_policy"] = "full-worktree"
            write_json(receipt_path, receipt)
            judge_run["receipt_sha256"] = digest(receipt_path)
            self.save_manifest(workspace, manifest)
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_run_directory_cannot_supply_its_own_trust_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            local_seal = workspace["run"] / "self-declared-seal.json"
            local_seal.write_bytes(workspace["trusted_seal"].read_bytes())
            with self.assertRaises(GateError):
                evaluate(
                    workspace["manifest"],
                    leakage_terms_path=workspace["leakage_terms"],
                    trusted_seal_path=local_seal,
                    repo_root=workspace["repo"],
                    corpus_path=workspace["corpus"],
                    config_path=workspace["config"],
                )

    def test_generation_prompt_must_equal_neutral_template(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            manifest = self.load_manifest(workspace)
            case = manifest["cases"][0]
            prompt = workspace["run"] / case["generation_prompt"]
            prompt.write_text("biased wrapper\n", encoding="utf-8")
            case["generation_prompt_sha256"] = digest(prompt)
            for replicate in case["replicates"]:
                for arm in ("baseline", "candidate"):
                    run = replicate["generation_runs"][arm]
                    receipt_path = workspace["run"] / run["receipt"]
                    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
                    receipt["prompt_sha256"] = digest(prompt)
                    write_json(receipt_path, receipt)
                    run["receipt_sha256"] = digest(receipt_path)
            self.save_manifest(workspace, manifest)
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_case_bytes_changed_after_seal_cannot_be_redeclared(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            corpus = json.loads(workspace["corpus"].read_text(encoding="utf-8"))
            spec = workspace["corpus"].parent / corpus["cases"][0]["case_spec"]
            spec.write_text("# Changed trusted brief\n", encoding="utf-8")
            manifest = self.load_manifest(workspace)
            manifest["provenance"]["corpus_bundle_sha256"] = corpus_bundle_sha256(
                workspace["corpus"]
            )
            manifest["holdout_seal"]["corpus_bundle_sha256"] = manifest[
                "provenance"
            ]["corpus_bundle_sha256"]
            self.save_manifest(workspace, manifest)
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_untrusted_leakage_term_set_invalidates_seal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            workspace["leakage_terms"].write_text(
                "\n".join(f"replacement-token-{index}" for index in range(8))
                + "\n",
                encoding="utf-8",
            )
            manifest = self.load_manifest(workspace)
            manifest["provenance"]["leakage_terms_sha256"] = digest(
                workspace["leakage_terms"]
            )
            manifest["holdout_seal"]["leakage_terms_sha256"] = manifest[
                "provenance"
            ]["leakage_terms_sha256"]
            self.save_manifest(workspace, manifest)
            with self.assertRaises(GateError):
                self.evaluate_workspace(workspace)

    def test_private_term_in_release_guidance_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))
            workspace["reviewer"].write_text(
                "review guidance sealed-private-token-0\n",
                encoding="utf-8",
            )
            result = self.evaluate_workspace(workspace)
        self.assertFalse(result["passed"])
        self.assertEqual(
            result["release_leakage_files"],
            ["skills/short-drama-review/rubric.md"],
        )

    def test_private_term_in_candidate_artifact_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory), candidate_leak_case=0)
            result = self.evaluate_workspace(workspace)
        self.assertFalse(result["passed"])
        self.assertEqual(result["candidate_leakage_cases"], ["case-1"])

    def test_negative_control_overfit_diagnostic_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))

            def add_flag(report: dict, run: dict) -> None:
                baseline_label = run["baseline_label"]
                candidate_label = "B" if baseline_label == "A" else "A"
                report["diagnostics"][candidate_label] = {
                    "overfit_flags": ["forced_choice"],
                    "overfit_evidence": {"forced_choice": "invented dilemma"},
                }

            self.mutate_report(workspace, 1, 0, 0, add_flag)
            result = self.evaluate_workspace(workspace)
        self.assertFalse(result["passed"])
        self.assertEqual(result["negative_control_candidate_overfit_flags"], 1)

    def test_replicates_are_equal_weighted_before_case_aggregation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory))

            def lower_candidate(report: dict, run: dict) -> None:
                baseline_label = run["baseline_label"]
                candidate_label = "B" if baseline_label == "A" else "A"
                report["scores"][candidate_label] = distributed_score(45)
                report["preference"] = baseline_label

            for run_index in range(4):
                self.mutate_report(workspace, 0, 0, run_index, lower_candidate)
            result = self.evaluate_workspace(workspace)
        first_case = result["cases"][0]
        self.assertEqual(first_case["replicate_count"], REPLICATE_COUNT)
        self.assertEqual(first_case["baseline_mean"], 70.0)
        self.assertEqual(first_case["candidate_mean"], 65.0)
        self.assertFalse(first_case["non_material_regression"])

    def test_material_case_regression_fails_even_when_macro_improves(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = self.build_workspace(Path(directory), candidate_total=80)

            def lower_candidate(report: dict, run: dict) -> None:
                baseline_label = run["baseline_label"]
                candidate_label = "B" if baseline_label == "A" else "A"
                report["scores"][candidate_label] = distributed_score(60)
                report["preference"] = baseline_label

            for replicate_index in range(REPLICATE_COUNT):
                for run_index in range(4):
                    self.mutate_report(
                        workspace,
                        0,
                        replicate_index,
                        run_index,
                        lower_candidate,
                    )
            result = self.evaluate_workspace(workspace)
        self.assertFalse(result["passed"])
        self.assertFalse(result["cases"][0]["non_material_regression"])


if __name__ == "__main__":
    unittest.main()
