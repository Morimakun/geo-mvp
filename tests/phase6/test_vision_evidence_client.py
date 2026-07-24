"""Step 3B: Vision evidence client のテスト（モックのみ。実APIは一切呼ばない）。

設計根拠: docs/PHASE_6_TRIPLE_EVIDENCE_SCHEMA_DESIGN_REVIEW.md 第4版
         および Step 3B実装指示（2026-07-23）、Step 3B v1パイロット後の修正指示（2026-07-23）

CSV resolverとの結合・三者比較・review routing・UI・66ページ一括処理・
phase6_stage3_full.pyへの変更には一切触れない（本モジュールのスコープ外）。

すべてのテストはunittest.mock.MagicMockでAnthropicクライアントを差し替え、
実際のVision API呼び出しは一切行わない（PDFの読み込み・画像レンダリングは
ローカル処理のため実際に行われる）。
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.phase6.vision_evidence_client import (  # noqa: E402
    SOURCE_PDF_SHA256,
    VISION_EVIDENCE_CONTRACT_VERSION,
    VISION_EVIDENCE_PROMPT_VERSION,
    VISION_MAX_TOKENS,
    VISION_TOOL_NAME,
    regions_for_page,
    run_vision_evidence_pilot_page,
)
from src.phase6.vision_evidence_contract import VisionEvidenceContractError  # noqa: E402

BUSINESS_DATE = date(2026, 6, 25)
RUN_ID = "test_run"


def _valid_payload(*, page_no: int = 59, form_version: str = "new") -> dict:
    regions = regions_for_page(page_no, form_version)
    payload = {
        "page_no": page_no,
        "form_version": form_version,
        "intro": {
            "written_total": {
                "value": 0,
                "status": "observed",
                "confidence": "high",
                "notes": "",
                "region_id": "intro_written_total_region",
            },
            "tally": {
                "observation_status": "no_marks_observed",
                "complete_five_groups": None,
                "remainder_strokes": None,
                "confidence": "medium",
                "notes": "",
                "components": [],
                "region_id": "intro_tally_region",
            },
        },
        "voice": {
            "written_total": {
                "value": 0,
                "status": "observed",
                "confidence": "high",
                "notes": "",
                "region_id": "voice_written_total_region",
            },
            "tally": {
                "observation_status": "no_marks_observed",
                "complete_five_groups": None,
                "remainder_strokes": None,
                "confidence": "medium",
                "notes": "",
                "components": [],
                "region_id": "voice_tally_region",
            },
        },
    }
    if "store_code_region" in regions:
        payload["store_code"] = {
            "raw_value": "AU1K000000",
            "status": "observed",
            "confidence": "high",
            "notes": "",
            "region_id": "store_code_region",
        }
    return payload


def _fake_tool_message(
    payload: dict,
    *,
    stop_reason: str = "tool_use",
    input_tokens: int = 300,
    output_tokens: int = 120,
):
    tool_block = SimpleNamespace(type="tool_use", name=VISION_TOOL_NAME, input=payload)
    return SimpleNamespace(
        content=[tool_block],
        usage=SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason=stop_reason,
    )


def _fake_client_with_responses(responses: list) -> MagicMock:
    client = MagicMock()

    def _side_effect(*args, **kwargs):
        item = responses.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    client.messages.create.side_effect = _side_effect
    return client


class TestSuccessPath:
    def test_valid_response_is_parsed_into_page_evidence(self, tmp_path):
        payload = _valid_payload(page_no=59)
        client = _fake_client_with_responses([_fake_tool_message(payload)])

        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )

        assert audit["success"] is True
        assert audit["attempt_count"] == 1
        assert audit["page_evidence"]["page_no"] == 59
        assert client.messages.create.call_count == 1

    def test_tool_choice_and_max_tokens_are_sent(self, tmp_path):
        payload = _valid_payload(page_no=59)
        client = _fake_client_with_responses([_fake_tool_message(payload)])
        run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        _, kwargs = client.messages.create.call_args
        assert kwargs["max_tokens"] <= 2048
        assert kwargs["max_tokens"] == VISION_MAX_TOKENS
        assert kwargs["tool_choice"] == {"type": "tool", "name": VISION_TOOL_NAME}
        assert kwargs["tools"][0]["name"] == VISION_TOOL_NAME


class TestPerAttemptAudit:
    def test_first_failure_then_second_success_both_attempts_are_kept(self, tmp_path):
        bad_payload = _valid_payload(page_no=59)
        bad_payload["store_code"]["status"] = "totally_unknown_status"
        good_payload = _valid_payload(page_no=59)
        client = _fake_client_with_responses(
            [_fake_tool_message(bad_payload), _fake_tool_message(good_payload)]
        )
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        assert audit["success"] is True
        assert audit["attempt_count"] == 2
        assert len(audit["attempts"]) == 2
        assert audit["attempts"][0]["success"] is False
        assert audit["attempts"][0]["error_type"] == "VisionEvidenceContractError"
        assert audit["attempts"][0]["parsed_payload"]["store_code"]["status"] == "totally_unknown_status"
        assert audit["attempts"][1]["success"] is True
        # 2回目成功後も1回目の失敗記録が消えていないことを確認
        assert audit["attempts"][0]["error_message"] is not None

    def test_both_attempts_fail_both_are_kept(self, tmp_path):
        bad_payload = _valid_payload(page_no=59)
        bad_payload["store_code"]["status"] = "totally_unknown_status"
        client = _fake_client_with_responses(
            [_fake_tool_message(bad_payload), _fake_tool_message(bad_payload)]
        )
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        assert audit["success"] is False
        assert audit["attempt_count"] == 2
        assert len(audit["attempts"]) == 2
        assert all(a["success"] is False for a in audit["attempts"])
        assert client.messages.create.call_count == 2  # 3回目は呼ばれない

    def test_raw_response_and_token_usage_are_kept_per_attempt(self, tmp_path):
        bad_payload = _valid_payload(page_no=59)
        bad_payload["store_code"]["status"] = "totally_unknown_status"
        good_payload = _valid_payload(page_no=59)
        client = _fake_client_with_responses(
            [
                _fake_tool_message(bad_payload, input_tokens=111, output_tokens=22),
                _fake_tool_message(good_payload, input_tokens=333, output_tokens=44),
            ]
        )
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        a1, a2 = audit["attempts"]
        assert a1["input_tokens"] == 111
        assert a1["output_tokens"] == 22
        assert a1["raw_response_text"] is not None
        assert json.loads(a1["raw_response_text"])["store_code"]["status"] == "totally_unknown_status"
        assert a2["input_tokens"] == 333
        assert a2["output_tokens"] == 44
        assert a1["stop_reason"] == "tool_use"
        assert a1["model"] and a1["prompt_version"] and a1["contract_version"]

    def test_audit_file_on_disk_also_contains_all_attempts(self, tmp_path):
        bad_payload = _valid_payload(page_no=59)
        bad_payload["store_code"]["status"] = "totally_unknown_status"
        good_payload = _valid_payload(page_no=59)
        client = _fake_client_with_responses(
            [_fake_tool_message(bad_payload), _fake_tool_message(good_payload)]
        )
        run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        audit_path = tmp_path / RUN_ID / "audit" / "p59_audit.json"
        saved = json.loads(audit_path.read_text(encoding="utf-8"))
        assert len(saved["attempts"]) == 2


class TestApiExceptions:
    def test_transient_api_exception_retries_then_fails(self, tmp_path):
        client = _fake_client_with_responses(
            [
                anthropic.APIConnectionError(request=MagicMock()),
                anthropic.APIConnectionError(request=MagicMock()),
            ]
        )
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        assert audit["success"] is False
        assert audit["attempt_count"] == 2
        assert all(a["error_type"] == "APIConnectionError" for a in audit["attempts"])

    def test_non_retryable_auth_error_does_not_retry(self, tmp_path):
        auth_error = anthropic.AuthenticationError(
            "invalid api key", response=MagicMock(status_code=401), body=None
        )
        client = _fake_client_with_responses([auth_error])
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        assert audit["success"] is False
        assert audit["attempt_count"] == 1
        assert client.messages.create.call_count == 1


class TestRegionAttributionRejection:
    def test_response_referencing_unsent_region_id_is_rejected(self, tmp_path):
        payload = _valid_payload(page_no=59)
        payload["intro"]["tally"]["region_id"] = "some_region_never_sent"
        client = _fake_client_with_responses(
            [_fake_tool_message(payload), _fake_tool_message(payload)]
        )
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        assert audit["success"] is False
        assert all(a["error_type"] == "VisionEvidenceContractError" for a in audit["attempts"])
        assert "some_region_never_sent" in audit["attempts"][0]["error_message"]

    def test_response_using_correct_region_ids_succeeds(self, tmp_path):
        payload = _valid_payload(page_no=59)
        client = _fake_client_with_responses([_fake_tool_message(payload)])
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        assert audit["success"] is True

    def test_old_form_page_has_no_store_code_region_and_still_succeeds(self, tmp_path):
        payload = _valid_payload(page_no=66, form_version="old")
        client = _fake_client_with_responses([_fake_tool_message(payload)])
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=66,
            expected_form_version="old",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        assert audit["success"] is True
        assert "store_code" not in payload  # 旧帳票にはstore_code_regionを送っていない


class TestAuditRecordSafety:
    def test_audit_record_contains_versions_and_pdf_sha256(self, tmp_path):
        payload = _valid_payload(page_no=59)
        client = _fake_client_with_responses([_fake_tool_message(payload)])
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        assert audit["contract_version"] == VISION_EVIDENCE_CONTRACT_VERSION
        assert audit["prompt_version"] == VISION_EVIDENCE_PROMPT_VERSION
        assert audit["source_pdf_sha256"] == SOURCE_PDF_SHA256
        assert audit["run_id"] == RUN_ID

    def test_image_sha256_in_audit_matches_crop_manifest(self, tmp_path):
        payload = _valid_payload(page_no=59)
        client = _fake_client_with_responses([_fake_tool_message(payload)])
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        manifest_sha256 = sorted(img["sha256"] for img in audit["images"])
        attempt_sha256 = sorted(audit["attempts"][0]["image_sha256_list"])
        assert manifest_sha256 == attempt_sha256
        assert len(manifest_sha256) == len(audit["images"])
        for img in audit["images"]:
            assert len(img["sha256"]) == 64
            # 画像ファイルが実際に保存され、そのSHA-256がmanifestと一致すること
            saved_path = tmp_path / RUN_ID / "images" / img["filename"]
            assert saved_path.exists()

    def test_audit_json_never_contains_api_key_or_base64(self, tmp_path):
        payload = _valid_payload(page_no=59)
        client = _fake_client_with_responses([_fake_tool_message(payload)])
        audit = run_vision_evidence_pilot_page(
            client,
            run_id=RUN_ID,
            pdf_page_no=59,
            expected_form_version="new",
            selected_business_date=BUSINESS_DATE,
            output_dir=tmp_path,
        )
        serialized = json.dumps(audit, ensure_ascii=False)
        assert "api_key" not in serialized.lower()
        assert "sk-ant" not in serialized
        for image_record in audit["images"]:
            assert "image_bytes" not in image_record
            assert "data" not in image_record

        audit_path = tmp_path / RUN_ID / "audit" / "p59_audit.json"
        saved_text = audit_path.read_text(encoding="utf-8")
        assert "api_key" not in saved_text.lower()
        assert "sk-ant" not in saved_text
