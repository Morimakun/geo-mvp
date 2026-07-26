"""src/phase6/vision_evidence_quality_gate.py および
scripts/check_phase6_v3_audit.py のテスト。

実データ（実PDF・実Excel・実Vision API応答）は一切使用しない。すべて合成した
監査JSON（dict）とtmp_pathのみでテストする。
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.phase6.vision_evidence_contract import VISION_EVIDENCE_CONTRACT_VERSION  # noqa: E402
from src.phase6.vision_evidence_prompt import VISION_EVIDENCE_PROMPT_VERSION  # noqa: E402
from src.phase6.vision_evidence_quality_gate import (  # noqa: E402
    check_general_quality_gate,
    check_p59_profile,
)
from scripts.check_phase6_v3_audit import main  # noqa: E402


# ============================================================
# 合成監査JSONの構築ヘルパー
# ============================================================
def _numeric_field(value: int) -> dict:
    return {
        "written_total": {"value": value, "status": "observed", "confidence": "high", "notes": ""},
        "tally": {
            "observation_status": "no_marks_observed",
            "complete_five_groups": None,
            "remainder_strokes": None,
            "tally_count": None,
            "confidence": "medium",
            "notes": "",
            "components": [],
        },
        "cell_representation": "numeric",
    }


def _blank_field() -> dict:
    return {
        "written_total": {"value": None, "status": "no_value", "confidence": None, "notes": ""},
        "tally": {
            "observation_status": "no_marks_observed",
            "complete_five_groups": None,
            "remainder_strokes": None,
            "tally_count": None,
            "confidence": None,
            "notes": "",
            "components": [],
        },
        "cell_representation": "blank",
    }


def _valid_page_evidence(*, page_no: int = 59, intro_value: int = 0) -> dict:
    return {
        "page_no": page_no,
        "form_version": "new",
        "selected_business_date": "2026-06-25",
        "store_code_evidence": {
            "raw_value": "AU1K0000000",
            "normalized_value": None,
            "status": "observed",
            "confidence": "high",
            "format_status": "unknown",
            "notes": "",
        },
        "intro_evidence": _numeric_field(intro_value),
        "voice_evidence": _blank_field(),
        "intro_total": intro_value,
        "voice_callout_total": None,
    }


def _valid_attempt() -> dict:
    return {
        "attempt_number": 1,
        "request_timestamp_utc": "2026-07-26T00:00:00+00:00",
        "success": True,
        "error_type": None,
        "error_message": None,
        "raw_response_text": "{}",
        "parsed_payload": {},
        "input_tokens": 321,
        "output_tokens": 64,
        "stop_reason": "tool_use",
        "model": "claude-sonnet-5",
        "prompt_version": VISION_EVIDENCE_PROMPT_VERSION,
        "contract_version": VISION_EVIDENCE_CONTRACT_VERSION,
        "image_sha256_list": ["a" * 64, "b" * 64],
    }


def _valid_audit(**overrides) -> dict:
    audit = {
        "run_id": "step3b_pilot_v3_synthetic_test",
        "page_no": 59,
        "expected_form_version": "new",
        "selected_business_date": "2026-06-25",
        "contract_version": VISION_EVIDENCE_CONTRACT_VERSION,
        "prompt_version": VISION_EVIDENCE_PROMPT_VERSION,
        "model": "claude-sonnet-5",
        "max_tokens": 2048,
        "registration": {
            "template_id": "synthetic_anchor",
            "x_offset": 0,
            "y_offset": 0,
            "score": 0.99,
            "status": "matched",
            "basis": "synthetic test basis",
        },
        "success": True,
        "attempt_count": 1,
        "page_evidence": _valid_page_evidence(),
        "attempts": [_valid_attempt()],
    }
    audit.update(overrides)
    return audit


def _results_dict(results: list) -> dict:
    return {name: passed for name, passed, _detail in results}


# ============================================================
# 一般品質ゲート: 正常系
# ============================================================
class TestGeneralQualityGateValid:
    def test_valid_audit_passes_all_checks(self):
        results = check_general_quality_gate(_valid_audit())
        assert results, "結果が空であってはならない"
        assert all(passed for _n, passed, _d in results)

    def test_numeric_zero_is_allowed(self):
        audit = _valid_audit(page_evidence=_valid_page_evidence(intro_value=0))
        d = _results_dict(check_general_quality_gate(audit))
        assert d["intro_numeric_written_total_value_present"] is True
        assert d["intro_numeric_written_total_observed"] is True


# ============================================================
# 一般品質ゲート: 異常系
# ============================================================
class TestGeneralQualityGateInvalid:
    def test_audit_not_a_dict_fails(self):
        results = check_general_quality_gate(["not", "a", "dict"])
        d = _results_dict(results)
        assert d["audit_is_dict"] is False

    @pytest.mark.parametrize("status", ["low_confidence", "failed"])
    def test_registration_not_matched_fails(self, status):
        audit = _valid_audit()
        audit["registration"]["status"] = status
        d = _results_dict(check_general_quality_gate(audit))
        assert d["registration_matched"] is False

    def test_success_false_fails(self):
        audit = _valid_audit(success=False)
        d = _results_dict(check_general_quality_gate(audit))
        assert d["success_true"] is False

    def test_attempt_count_not_1_fails(self):
        audit = _valid_audit(attempt_count=2)
        d = _results_dict(check_general_quality_gate(audit))
        assert d["attempt_count_is_1"] is False

    def test_zero_attempts_fails(self):
        audit = _valid_audit(attempts=[])
        d = _results_dict(check_general_quality_gate(audit))
        assert d["attempts_has_exactly_one_entry"] is False
        assert d["attempt_0_success_true"] is False

    def test_two_attempts_fails(self):
        audit = _valid_audit(attempts=[_valid_attempt(), _valid_attempt()])
        d = _results_dict(check_general_quality_gate(audit))
        assert d["attempts_has_exactly_one_entry"] is False

    def test_attempt_0_not_successful_fails(self):
        attempt = _valid_attempt()
        attempt["success"] = False
        audit = _valid_audit(attempts=[attempt])
        d = _results_dict(check_general_quality_gate(audit))
        assert d["attempt_0_success_true"] is False

    def test_contract_version_mismatch_fails(self):
        audit = _valid_audit(contract_version="1.0.0")
        d = _results_dict(check_general_quality_gate(audit))
        assert d["contract_version_matches"] is False

    def test_prompt_version_mismatch_fails(self):
        audit = _valid_audit(prompt_version="2.0.0")
        d = _results_dict(check_general_quality_gate(audit))
        assert d["prompt_version_matches"] is False

    def test_page_evidence_missing_fails(self):
        audit = _valid_audit(page_evidence=None)
        d = _results_dict(check_general_quality_gate(audit))
        assert d["page_evidence_present"] is False
        assert d["intro_evidence_present"] is False
        assert d["voice_evidence_present"] is False

    def test_intro_cell_representation_none_fails(self):
        audit = _valid_audit()
        audit["page_evidence"]["intro_evidence"]["cell_representation"] = None
        d = _results_dict(check_general_quality_gate(audit))
        assert d["intro_cell_representation_present"] is False

    def test_intro_cell_representation_inconsistent_with_written_and_tally_fails(self):
        # cell_representation=numericと自己申告しているが、tallyがmarks_present
        # （矛盾）。既存のevidence_schema.NumericFieldEvidenceの検証にそのまま委譲され、
        # このモジュールで矛盾判定ロジックを再実装していないことを確認する。
        audit = _valid_audit()
        audit["page_evidence"]["intro_evidence"]["tally"] = {
            "observation_status": "marks_present",
            "complete_five_groups": 1,
            "remainder_strokes": 0,
            "tally_count": 5,
            "confidence": "high",
            "notes": "",
            "components": [],
        }
        d = _results_dict(check_general_quality_gate(audit))
        assert d["intro_cell_representation_consistent"] is False

    def test_secret_like_field_is_detected(self):
        audit = _valid_audit()
        audit["attempts"][0]["api_key"] = "dummy-secret-value"
        d = _results_dict(check_general_quality_gate(audit))
        assert d["no_secret_like_fields"] is False

    def test_base64_like_image_payload_is_detected(self):
        audit = _valid_audit()
        audit["attempts"][0]["stray_field"] = "A" * 400  # base64っぽい非常に長い文字列
        d = _results_dict(check_general_quality_gate(audit))
        assert d["no_image_data_only_sha256"] is False

    def test_forbidden_image_key_name_is_detected(self):
        audit = _valid_audit()
        audit["attempts"][0]["image_bytes"] = "short"
        d = _results_dict(check_general_quality_gate(audit))
        assert d["no_image_data_only_sha256"] is False

    def test_sha256_hex_strings_alone_do_not_trigger_base64_detection(self):
        # image_sha256_listの64桁16進文字列自体は200文字未満なので誤検出しないこと。
        audit = _valid_audit()
        d = _results_dict(check_general_quality_gate(audit))
        assert d["no_image_data_only_sha256"] is True


# ============================================================
# P59限定プロフィール
# ============================================================
class TestP59Profile:
    def test_valid_p59_audit_passes(self):
        results = check_p59_profile(_valid_audit())
        assert results
        assert all(passed for _n, passed, _d in results)

    def test_wrong_page_no_fails(self):
        audit = _valid_audit(page_no=32)
        d = _results_dict(check_p59_profile(audit))
        assert d["page_no_is_59"] is False

    def test_wrong_form_version_fails(self):
        audit = _valid_audit(expected_form_version="old")
        d = _results_dict(check_p59_profile(audit))
        assert d["expected_form_version_is_new"] is False

    def test_wrong_business_date_fails(self):
        audit = _valid_audit(selected_business_date="2026-06-26")
        d = _results_dict(check_p59_profile(audit))
        assert d["selected_business_date_matches"] is False

    def test_intro_written_total_not_zero_fails(self):
        audit = _valid_audit(page_evidence=_valid_page_evidence(intro_value=1))
        d = _results_dict(check_p59_profile(audit))
        assert d["intro_written_total_value_is_0"] is False

    def test_intro_tally_not_no_marks_observed_fails(self):
        audit = _valid_audit()
        audit["page_evidence"]["intro_evidence"]["tally"]["observation_status"] = "unreadable"
        d = _results_dict(check_p59_profile(audit))
        assert d["intro_tally_observation_status_is_no_marks_observed"] is False

    def test_missing_page_evidence_fails_gracefully(self):
        audit = _valid_audit(page_evidence=None)
        results = check_p59_profile(audit)
        d = _results_dict(results)
        assert d["intro_profile_checkable"] is False
        assert results  # 空にならず、明示的な失敗理由が返ること

    def test_voice_and_store_code_are_never_referenced(self):
        # お声がけ値・店舗コードを大きく変えても、P59限定プロフィールの結果は
        # 一切変化しないこと（採点対象外であることの裏付け）。
        baseline_audit = _valid_audit()
        baseline_results = check_p59_profile(baseline_audit)

        mutated_audit = copy.deepcopy(baseline_audit)
        mutated_audit["page_evidence"]["voice_evidence"] = _numeric_field(999)
        mutated_audit["page_evidence"]["store_code_evidence"]["raw_value"] = "COMPLETELY_DIFFERENT"
        mutated_results = check_p59_profile(mutated_audit)

        assert baseline_results == mutated_results


# ============================================================
# CLI（scripts/check_phase6_v3_audit.py）
# ============================================================
class TestCli:
    def _write_audit(self, tmp_path: Path, audit: dict, *, name: str = "audit.json") -> Path:
        path = tmp_path / name
        path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def test_cli_exits_zero_for_valid_audit(self, tmp_path, capsys):
        audit_path = self._write_audit(tmp_path, _valid_audit())
        exit_code = main(["--audit", str(audit_path)])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "合格" in captured.out

    def test_cli_exits_one_for_invalid_audit(self, tmp_path, capsys):
        audit_path = self._write_audit(tmp_path, _valid_audit(success=False))
        exit_code = main(["--audit", str(audit_path)])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert "NG: success_true" in captured.out

    def test_cli_with_p59_profile_combines_both_check_sets(self, tmp_path, capsys):
        audit_path = self._write_audit(tmp_path, _valid_audit())
        exit_code = main(["--audit", str(audit_path), "--profile", "p59"])
        captured = capsys.readouterr()
        assert exit_code == 0
        assert "OK: registration_matched" in captured.out
        assert "OK: intro_written_total_value_is_0" in captured.out

    def test_cli_missing_audit_file_exits_one(self, tmp_path, capsys):
        missing = tmp_path / "does_not_exist.json"
        exit_code = main(["--audit", str(missing)])
        captured = capsys.readouterr()
        assert exit_code == 1
        assert captured.err  # エラー理由が明示されること

    def test_cli_malformed_json_exits_one(self, tmp_path, capsys):
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{not valid json", encoding="utf-8")
        exit_code = main(["--audit", str(bad_path)])
        captured = capsys.readouterr()
        assert exit_code == 1

    def test_cli_does_not_modify_audit_file(self, tmp_path):
        audit_path = self._write_audit(tmp_path, _valid_audit())
        before = audit_path.read_bytes()

        main(["--audit", str(audit_path)])

        after = audit_path.read_bytes()
        assert before == after

    def test_cli_does_not_create_extra_files(self, tmp_path):
        audit_path = self._write_audit(tmp_path, _valid_audit())
        before = set(tmp_path.iterdir())

        main(["--audit", str(audit_path)])

        after = set(tmp_path.iterdir())
        assert before == after
