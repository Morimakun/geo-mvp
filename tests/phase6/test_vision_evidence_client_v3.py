"""Step 3B v3: Vision抽出クライアント(vision_evidence_client_v3.py)のテスト。

実PDF・実Excel・実Vision APIは一切使用しない。ページ画像は合成画像
（PIL生成の架空マーカー）、Vision応答はモック（メモリ上のfake client）で用意する。
これは "既存の実PDF依存テストを、可能な範囲でtmp_pathに生成した合成画像へ
置き換える" というStep 3B v3実装指示の一部であり、v2（vision_evidence_client.py、
実PDF依存）とは別のテストファイルとして独立させている。
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
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.phase6.evidence_schema import EvidenceValidationError  # noqa: E402
from src.phase6.page_registration import (  # noqa: E402
    CellRegionPair,
    RegionDefinition,
    RegistrationStatus,
    StoreCodeRegionPair,
    extract_anchor_template,
)
from src.phase6.vision_evidence_client_v3 import (  # noqa: E402
    RegistrationGateError,
    VisionApiCallErrorV3,
    _VISION_TOOL_NAME_V3,  # noqa: PLC2701 - 内部定数をfakeレスポンス組み立てに直接使う
    run_vision_evidence_pilot_page_v3,
)
from src.phase6.vision_evidence_contract import VisionEvidenceContractError  # noqa: E402

CANVAS_SIZE = (300, 300)
MARKER_SIZE = 20
MARKER_X = 150
MARKER_Y = 150
RUN_ID = "step3b_pilot_v3_test"
PAGE_NO = 999
BUSINESS_DATE = date(2026, 6, 26)


# ============================================================
# 合成画像・領域構造のヘルパー
# ============================================================
def _blank_canvas(fill: int = 255) -> Image.Image:
    return Image.new("RGB", CANVAS_SIZE, color=(fill, fill, fill))


def _canvas_with_marker(*, x: int, y: int, fill: int = 0, size: int = MARKER_SIZE) -> Image.Image:
    img = _blank_canvas()
    draw = ImageDraw.Draw(img)
    draw.rectangle([x, y, x + size - 1, y + size - 1], fill=(fill, fill, fill))
    return img


def _reference_template():
    reference_image = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)
    return extract_anchor_template(
        reference_image, template_id="synthetic_v3_anchor", x=MARKER_X, y=MARKER_Y, width=MARKER_SIZE, height=MARKER_SIZE
    )


def _cell_region_pairs() -> dict:
    return {
        "intro": CellRegionPair(
            cell_id="intro",
            cell_context_region=RegionDefinition("intro__context", 20, 20, 60, 40),
            cell_detail_region=RegionDefinition("intro__detail", 30, 30, 20, 15),
        ),
        "voice": CellRegionPair(
            cell_id="voice",
            cell_context_region=RegionDefinition("voice__context", 100, 20, 60, 40),
            cell_detail_region=RegionDefinition("voice__detail", 110, 30, 20, 15),
        ),
    }


def _store_code_region_pair() -> StoreCodeRegionPair:
    return StoreCodeRegionPair(
        store_code_context_region=RegionDefinition("store_code__context", 20, 80, 120, 20),
        store_code_detail_region=RegionDefinition("store_code__detail", 25, 83, 80, 14),
    )


# ============================================================
# fake Anthropicクライアント
# ============================================================
def _fake_tool_message(payload: dict, *, stop_reason: str = "tool_use"):
    block = SimpleNamespace(type="tool_use", name=_VISION_TOOL_NAME_V3, input=payload)
    usage = SimpleNamespace(input_tokens=321, output_tokens=64)
    return SimpleNamespace(content=[block], usage=usage, stop_reason=stop_reason)


class _FakeMessages:
    def __init__(self, responses: list):
        self._responses = list(responses)
        self.call_count = 0
        self.calls: list = []

    def create(self, **kwargs):
        self.call_count += 1
        self.calls.append(kwargs)
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClient:
    def __init__(self, responses: list):
        self.messages = _FakeMessages(responses)


def _valid_payload_v3(*, page_no: int, form_version: str = "new", include_store_code: bool = True) -> dict:
    payload = {
        "page_no": page_no,
        "form_version": form_version,
        "intro": {
            "written_total": {"value": 3, "status": "observed", "confidence": "high", "notes": ""},
            "tally": {
                "observation_status": "no_marks_observed",
                "complete_five_groups": None,
                "remainder_strokes": None,
                "confidence": "medium",
                "notes": "",
                "components": [],
            },
            "cell_representation": "numeric",
            "cell_id": "intro",
        },
        "voice": {
            "written_total": {"value": None, "status": "no_value", "confidence": None, "notes": ""},
            "tally": {
                "observation_status": "no_marks_observed",
                "complete_five_groups": None,
                "remainder_strokes": None,
                "confidence": None,
                "notes": "",
                "components": [],
            },
            "cell_representation": "blank",
            "cell_id": "voice",
        },
    }
    if include_store_code:
        payload["store_code"] = {
            "raw_value": "AU1K000001",
            "status": "observed",
            "confidence": "high",
            "notes": "",
            "cell_id": "store_code",
        }
    return payload


def _run(client, *, target_image, tmp_path, form_version="new", include_store_code=True):
    return run_vision_evidence_pilot_page_v3(
        client,
        run_id=RUN_ID,
        page_no=PAGE_NO,
        expected_form_version=form_version,
        selected_business_date=BUSINESS_DATE,
        target_image=target_image,
        anchor_template=_reference_template(),
        cell_region_pairs=_cell_region_pairs(),
        store_code_region_pair=_store_code_region_pair() if include_store_code else None,
        output_dir=tmp_path,
    )


# ============================================================
# 登録ゲート: matched -> Vision呼び出し可
# ============================================================
class TestRegistrationGateMatchedCallsVision:
    def test_matched_registration_calls_vision_and_succeeds(self, tmp_path):
        target_image = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)
        payload = _valid_payload_v3(page_no=PAGE_NO)
        client = _FakeClient([_fake_tool_message(payload)])

        audit = _run(client, target_image=target_image, tmp_path=tmp_path)

        assert client.messages.call_count == 1
        assert audit["registration"]["status"] == "matched"
        assert audit["success"] is True
        assert audit["page_evidence"]["intro_total"] == 3
        assert audit["attempt_count"] == 1
        assert len(audit["attempts"]) == 1
        assert audit["attempts"][0]["success"] is True


# ============================================================
# 登録ゲート: low_confidence/failed -> Visionを呼ばず構造化エラー
# ============================================================
class TestRegistrationGateBlocksVision:
    def test_low_confidence_registration_never_calls_vision(self, tmp_path):
        # マーカー位置は合っているが濃度が中間（degraded）でlow_confidenceになる。
        target_image = _canvas_with_marker(x=MARKER_X, y=MARKER_Y, fill=40)
        client = _FakeClient([])  # 応答を1件も用意しない（呼ばれたら即エラーになる）

        with pytest.raises(RegistrationGateError) as excinfo:
            _run(client, target_image=target_image, tmp_path=tmp_path)

        assert client.messages.call_count == 0
        assert excinfo.value.registration.status == RegistrationStatus.LOW_CONFIDENCE

    def test_failed_registration_never_calls_vision(self, tmp_path):
        target_image = _blank_canvas()  # マーカーが存在しない
        client = _FakeClient([])

        with pytest.raises(RegistrationGateError) as excinfo:
            _run(client, target_image=target_image, tmp_path=tmp_path)

        assert client.messages.call_count == 0
        assert excinfo.value.registration.status == RegistrationStatus.FAILED

    def test_gate_rejection_still_writes_audit_record_with_registration_info(self, tmp_path):
        target_image = _blank_canvas()
        client = _FakeClient([])

        with pytest.raises(RegistrationGateError):
            _run(client, target_image=target_image, tmp_path=tmp_path)

        audit_path = tmp_path / RUN_ID / "audit" / f"p{PAGE_NO:02d}_audit.json"
        assert audit_path.exists()
        saved = json.loads(audit_path.read_text(encoding="utf-8"))
        assert saved["success"] is False
        assert saved["registration"]["status"] == "failed"
        assert saved["attempts"] == []


# ============================================================
# cell_id自己申告の検証（対象外cell_idを拒否）
# ============================================================
class TestCellAttributionRejection:
    def test_response_referencing_unsent_cell_id_is_rejected(self, tmp_path):
        target_image = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)
        payload = _valid_payload_v3(page_no=PAGE_NO)
        payload["intro"]["cell_id"] = "voice"  # 送信済みだが自分のセルではない値
        client = _FakeClient([_fake_tool_message(payload)])

        audit = _run(client, target_image=target_image, tmp_path=tmp_path)

        assert audit["success"] is False
        assert audit["attempts"][0]["error_type"] == "VisionEvidenceContractError"
        # Vision自体は呼ばれている（応答の内容が拒否された、という違いを区別する）。
        assert client.messages.call_count == 1

    def test_response_using_correct_cell_ids_succeeds(self, tmp_path):
        target_image = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)
        payload = _valid_payload_v3(page_no=PAGE_NO)
        client = _FakeClient([_fake_tool_message(payload)])

        audit = _run(client, target_image=target_image, tmp_path=tmp_path)

        assert audit["success"] is True


# ============================================================
# attempt監査の維持
# ============================================================
class TestAttemptAudit:
    def test_failed_api_call_is_recorded_as_a_failed_attempt(self, tmp_path):
        target_image = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)
        auth_error = anthropic.AuthenticationError(
            "invalid api key", response=MagicMock(status_code=401), body=None
        )
        client = _FakeClient([auth_error])

        audit = _run(client, target_image=target_image, tmp_path=tmp_path)

        assert audit["success"] is False
        assert audit["attempt_count"] == 1
        assert len(audit["attempts"]) == 1
        assert audit["attempts"][0]["error_type"] == "AuthenticationError"
        assert audit["attempts"][0]["success"] is False

    def test_semantic_validation_failure_is_recorded_as_a_failed_attempt(self, tmp_path):
        target_image = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)
        payload = _valid_payload_v3(page_no=PAGE_NO)
        # cell_representation=numericなのにtally=marks_present（矛盾）。
        payload["intro"]["tally"] = {
            "observation_status": "marks_present",
            "complete_five_groups": 1,
            "remainder_strokes": 0,
            "confidence": "high",
            "notes": "",
            "components": [],
        }
        client = _FakeClient([_fake_tool_message(payload)])

        audit = _run(client, target_image=target_image, tmp_path=tmp_path)

        assert audit["success"] is False
        assert audit["attempts"][0]["error_type"] == "EvidenceValidationError"


# ============================================================
# APIキー・base64を監査へ保存しない
# ============================================================
class TestAuditRecordSafety:
    def test_audit_json_never_contains_base64_or_api_key(self, tmp_path):
        target_image = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)
        payload = _valid_payload_v3(page_no=PAGE_NO)
        client = _FakeClient([_fake_tool_message(payload)])

        audit = _run(client, target_image=target_image, tmp_path=tmp_path)

        serialized = json.dumps(audit, ensure_ascii=False)
        assert "base64" not in serialized.lower()
        # sha256ハッシュ(16進64文字)のみが記録されていること。
        assert len(audit["attempts"][0]["image_sha256_list"]) > 0
        for digest in audit["attempts"][0]["image_sha256_list"]:
            assert len(digest) == 64
            int(digest, 16)  # 16進文字列であることの確認

    def test_client_call_did_not_receive_api_key_field(self, tmp_path):
        # fakeクライアントはAPIキーを持たない（messages.createへの引数にも一切現れない）。
        # 呼び出しに使われたkwargsの中にAPIキーらしき値が含まれていないことを確認する。
        target_image = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)
        payload = _valid_payload_v3(page_no=PAGE_NO)
        client = _FakeClient([_fake_tool_message(payload)])

        _run(client, target_image=target_image, tmp_path=tmp_path)

        assert "api_key" not in client.messages.calls[0]
