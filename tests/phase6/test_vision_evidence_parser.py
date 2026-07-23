"""Step 3A: Vision evidence parser のテスト。

設計根拠: docs/PHASE_6_TRIPLE_EVIDENCE_SCHEMA_DESIGN_REVIEW.md 第4版
         および Step 3A実装指示（2026-07-22, 2026-07-23修正）

Vision API呼び出し・CSV resolverとの結合・三者比較・review routing・UIには
一切触れない（本モジュールのスコープ外）。

P41・P66については、確認できていない正の字の状態を推測でfixtureへ入れない
（ユーザー指示）。fixtureはtests/phase6/fixtures/vision_evidence/ に格納する。
実データ（P32の店舗コード等）はtests/fixtures配下にのみ保持し、
EXAMPLE_VISION_EVIDENCE_PAYLOAD（ソースツリー側）は架空値のみを使う。
"""

from __future__ import annotations

import copy
import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.phase6.evidence_schema import (  # noqa: E402
    EvidenceStatus,
    EvidenceValidationError,
    TallyObservationStatus,
)
from src.phase6.vision_evidence_contract import (  # noqa: E402
    EXAMPLE_VISION_EVIDENCE_PAYLOAD,
    VISION_EVIDENCE_CONTRACT_VERSION,
    VisionEvidenceContractError,
)
from src.phase6.vision_evidence_parser import (  # noqa: E402
    parse_vision_evidence_response,
    parse_vision_evidence_response_with_audit,
)
from src.phase6.vision_evidence_prompt import VISION_EVIDENCE_PROMPT_VERSION  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "vision_evidence"
BUSINESS_DATE = date(2026, 6, 26)

# EXAMPLE_VISION_EVIDENCE_PAYLOADの架空値と対応させる既知メタデータ。
EXAMPLE_PAGE_NO = 1
EXAMPLE_FORM_VERSION = "new"


def _example_payload() -> dict:
    return copy.deepcopy(EXAMPLE_VISION_EVIDENCE_PAYLOAD)


def _parse_example(payload: dict, **overrides):
    kwargs = dict(
        expected_page_no=EXAMPLE_PAGE_NO,
        expected_form_version=EXAMPLE_FORM_VERSION,
        selected_business_date=BUSINESS_DATE,
    )
    kwargs.update(overrides)
    return parse_vision_evidence_response(payload, **kwargs)


def _load_fixture(*parts: str) -> dict:
    with open(FIXTURES_DIR.joinpath(*parts), encoding="utf-8") as f:
        return json.load(f)


# ============================================================
# 実データ汚染防止
# ============================================================
class TestExamplePayloadIsFictional:
    def test_example_payload_does_not_contain_real_p32_values(self):
        payload = EXAMPLE_VISION_EVIDENCE_PAYLOAD
        assert payload["page_no"] != 32
        assert payload["store_code"]["raw_value"] != "4330093"


# ============================================================
# 正常系
# ============================================================
class TestNormalCases:
    def test_marks_present_five_groups_1_remainder_2_computed_in_python(self):
        payload = _example_payload()
        payload["intro"]["tally"] = {
            "observation_status": "marks_present",
            "complete_five_groups": 1,
            "remainder_strokes": 2,
            "confidence": "high",
            "notes": "",
            "components": [],
        }
        page = _parse_example(payload)
        assert page.intro_evidence.tally.tally_count == 7

    def test_intro_and_voice_are_independent(self):
        payload = _example_payload()
        payload["intro"]["written_total"]["value"] = 5
        payload["voice"]["written_total"]["value"] = 9
        page = _parse_example(payload)
        assert page.intro_total == 5
        assert page.voice_callout_total == 9

    def test_written_total_zero_is_preserved(self):
        payload = _example_payload()
        payload["intro"]["written_total"]["value"] = 0
        page = _parse_example(payload)
        assert page.intro_total == 0
        assert page.intro_evidence.written_total.status == EvidenceStatus.OBSERVED

    def test_no_marks_observed_gives_null_tally_count(self):
        payload = _example_payload()
        page = _parse_example(payload)
        assert page.intro_evidence.tally.observation_status == TallyObservationStatus.NO_MARKS_OBSERVED
        assert page.intro_evidence.tally.tally_count is None

    def test_unreadable_gives_null_tally_count(self):
        payload = _example_payload()
        payload["voice"]["tally"] = {
            "observation_status": "unreadable",
            "complete_five_groups": None,
            "remainder_strokes": None,
            "confidence": None,
            "notes": "",
            "components": [],
        }
        page = _parse_example(payload)
        assert page.voice_evidence.tally.observation_status == TallyObservationStatus.UNREADABLE
        assert page.voice_evidence.tally.tally_count is None

    def test_store_code_is_not_dropped(self):
        payload = _example_payload()
        payload["store_code"]["raw_value"] = "AU1K123456"
        page = _parse_example(payload)
        assert page.store_code_evidence.raw_value == "AU1K123456"

    def test_page_evidence_is_json_serializable(self):
        payload = _example_payload()
        page = _parse_example(payload)
        serialized = json.dumps(page.to_dict(include_legacy=True))
        restored = json.loads(serialized)
        assert restored["store_code_evidence"]["raw_value"] == payload["store_code"]["raw_value"]

    def test_page_no_and_form_version_come_from_expected_args(self):
        payload = _example_payload()
        page = _parse_example(payload, expected_page_no=EXAMPLE_PAGE_NO)
        assert page.page_no == EXAMPLE_PAGE_NO
        assert page.form_version == EXAMPLE_FORM_VERSION


# ============================================================
# 異常系
# ============================================================
class TestAbnormalCases:
    def test_bool_is_not_accepted_as_numeric_value(self):
        payload = _example_payload()
        payload["intro"]["written_total"]["value"] = True
        with pytest.raises(VisionEvidenceContractError):
            _parse_example(payload)

    def test_float_is_not_coerced_to_int(self):
        payload = _example_payload()
        payload["intro"]["tally"] = {
            "observation_status": "marks_present",
            "complete_five_groups": 2.0,
            "remainder_strokes": 0,
            "confidence": None,
            "notes": "",
            "components": [],
        }
        with pytest.raises(VisionEvidenceContractError):
            _parse_example(payload)

    def test_remainder_5_or_more_is_rejected(self):
        payload = _example_payload()
        payload["intro"]["tally"] = {
            "observation_status": "marks_present",
            "complete_five_groups": 0,
            "remainder_strokes": 5,
            "confidence": None,
            "notes": "",
            "components": [],
        }
        with pytest.raises(EvidenceValidationError):
            _parse_example(payload)

    def test_negative_number_is_rejected(self):
        payload = _example_payload()
        payload["intro"]["tally"] = {
            "observation_status": "marks_present",
            "complete_five_groups": -1,
            "remainder_strokes": 0,
            "confidence": None,
            "notes": "",
            "components": [],
        }
        with pytest.raises(VisionEvidenceContractError):
            _parse_example(payload)

    def test_marks_present_without_numbers_raises(self):
        payload = _example_payload()
        payload["intro"]["tally"] = {
            "observation_status": "marks_present",
            "complete_five_groups": None,
            "remainder_strokes": None,
            "confidence": None,
            "notes": "",
            "components": [],
        }
        with pytest.raises(EvidenceValidationError):
            _parse_example(payload)

    def test_no_marks_observed_with_numbers_raises(self):
        payload = _example_payload()
        payload["intro"]["tally"] = {
            "observation_status": "no_marks_observed",
            "complete_five_groups": 1,
            "remainder_strokes": 0,
            "confidence": None,
            "notes": "",
            "components": [],
        }
        with pytest.raises(EvidenceValidationError):
            _parse_example(payload)

    def test_unknown_status_raises_contract_error(self):
        payload = _example_payload()
        payload["store_code"]["status"] = "totally_unknown_status"
        with pytest.raises(VisionEvidenceContractError):
            _parse_example(payload)

    def test_missing_required_key_raises_contract_error(self):
        payload = _example_payload()
        del payload["store_code"]["status"]
        with pytest.raises(VisionEvidenceContractError):
            _parse_example(payload)

    def test_selected_business_date_is_not_overridden_by_payload(self):
        payload = _example_payload()
        payload["selected_business_date"] = "1999-01-01"
        payload["business_date"] = "1999-01-01"
        page = _parse_example(payload)
        assert page.selected_business_date == "2026-06-26"

    def test_tally_count_in_payload_is_not_trusted(self):
        payload = _example_payload()
        payload["intro"]["tally"] = {
            "observation_status": "marks_present",
            "complete_five_groups": 1,
            "remainder_strokes": 2,
            "tally_count": 999,
            "confidence": None,
            "notes": "",
            "components": [],
        }
        page = _parse_example(payload)
        assert page.intro_evidence.tally.tally_count == 7

    def test_page_no_mismatch_raises_contract_error(self):
        payload = _example_payload()
        with pytest.raises(VisionEvidenceContractError):
            _parse_example(payload, expected_page_no=EXAMPLE_PAGE_NO + 1)

    def test_form_version_mismatch_raises_contract_error(self):
        payload = _example_payload()
        with pytest.raises(VisionEvidenceContractError):
            _parse_example(payload, expected_form_version="old")

    def test_not_observed_is_rejected_by_default(self):
        payload = _example_payload()
        payload["store_code"]["status"] = "not_observed"
        with pytest.raises(VisionEvidenceContractError):
            _parse_example(payload)

    def test_not_observed_tally_is_rejected_by_default(self):
        payload = _example_payload()
        payload["intro"]["tally"]["observation_status"] = "not_observed"
        with pytest.raises(VisionEvidenceContractError):
            _parse_example(payload)


class TestAuditRecord:
    def test_audit_record_keeps_raw_payload_separate_from_page_evidence(self):
        payload = _example_payload()
        record = parse_vision_evidence_response_with_audit(
            payload,
            expected_page_no=EXAMPLE_PAGE_NO,
            expected_form_version=EXAMPLE_FORM_VERSION,
            selected_business_date=BUSINESS_DATE,
        )
        assert record.page_evidence.store_code_evidence.raw_value == payload["store_code"]["raw_value"]
        assert record.raw_payload["store_code"]["raw_value"] == payload["store_code"]["raw_value"]
        assert "raw_payload" not in record.page_evidence.to_dict()

    def test_audit_record_holds_contract_and_prompt_versions(self):
        payload = _example_payload()
        record = parse_vision_evidence_response_with_audit(
            payload,
            expected_page_no=EXAMPLE_PAGE_NO,
            expected_form_version=EXAMPLE_FORM_VERSION,
            selected_business_date=BUSINESS_DATE,
        )
        assert record.contract_version == VISION_EVIDENCE_CONTRACT_VERSION
        assert record.prompt_version == VISION_EVIDENCE_PROMPT_VERSION


# ============================================================
# 旧JSON互換（legacy）: not_observedを明示的に許可する経路
# ============================================================
class TestLegacyCompatibility:
    def test_legacy_fixture_requires_allow_not_observed(self):
        payload = _load_fixture("legacy", "p41_legacy_ai_missed.json")
        with pytest.raises(VisionEvidenceContractError):
            parse_vision_evidence_response(
                payload,
                expected_page_no=41,
                expected_form_version="new",
                selected_business_date=date(2026, 6, 26),
            )

    def test_legacy_ai_missed_intro_total_does_not_become_zero(self):
        payload = _load_fixture("legacy", "p41_legacy_ai_missed.json")
        page = parse_vision_evidence_response(
            payload,
            expected_page_no=41,
            expected_form_version="new",
            selected_business_date=date(2026, 6, 26),
            allow_not_observed=True,
        )
        assert page.intro_total is None
        assert page.intro_evidence.written_total.status == EvidenceStatus.NOT_OBSERVED

    def test_p66_pending_observation_requires_allow_not_observed(self):
        # P66の正の字状態はStep 3Bの実画像抽出まで未確定。unreadable/no_marks_observed/
        # no_valueのいずれにも仮置きしないため、Vision結果ではないpending_observation
        # fixtureとして保持し、allow_not_observed=Trueでのみ読める。
        payload = _load_fixture("legacy", "pending_observation", "p66_pending.json")
        with pytest.raises(VisionEvidenceContractError):
            parse_vision_evidence_response(
                payload,
                expected_page_no=66,
                expected_form_version="old",
                selected_business_date=date(2026, 6, 25),
            )

    def test_p66_pending_observation_confirmed_fields_and_unconfirmed_tally(self):
        payload = _load_fixture("legacy", "pending_observation", "p66_pending.json")
        page = parse_vision_evidence_response(
            payload,
            expected_page_no=66,
            expected_form_version="old",
            selected_business_date=date(2026, 6, 25),
            allow_not_observed=True,
        )
        # 確認済みの事実（旧帳票には店舗コード欄自体が存在しない、紹介の記載合計=6）
        assert page.store_code_evidence.status == EvidenceStatus.NOT_APPLICABLE
        assert page.intro_total == 6
        # 未確認の正の字状態はnot_observedのまま。marks_present等の確定的な主張は行わない。
        assert page.intro_evidence.tally.observation_status == TallyObservationStatus.NOT_OBSERVED
        assert page.intro_evidence.tally.tally_count is None


# ============================================================
# 問題ページfixture
# ============================================================
class TestFixtureP32:
    def test_p32_store_code_correct_value_not_the_past_ai_misread(self):
        payload = _load_fixture("p32_correct.json")
        page = parse_vision_evidence_response(
            payload,
            expected_page_no=32,
            expected_form_version="new",
            selected_business_date=date(2026, 6, 26),
        )
        assert page.store_code_evidence.raw_value == "4330093"
        assert page.store_code_evidence.raw_value != "430093"
        assert page.intro_total == 1


class TestFixtureP41:
    def test_p41_confirmed_written_total_is_2(self):
        payload = _load_fixture("p41_confirmed.json")
        page = parse_vision_evidence_response(
            payload,
            expected_page_no=41,
            expected_form_version="new",
            selected_business_date=date(2026, 6, 26),
        )
        assert page.intro_total == 2


class TestFixtureP59:
    def test_p59_written_total_zero_no_marks_observed_null_count(self):
        payload = _load_fixture("p59.json")
        page = parse_vision_evidence_response(
            payload,
            expected_page_no=59,
            expected_form_version="new",
            selected_business_date=date(2026, 6, 25),
        )
        assert page.intro_total == 0
        assert page.intro_evidence.tally.observation_status == TallyObservationStatus.NO_MARKS_OBSERVED
        assert page.intro_evidence.tally.tally_count is None


# P66の実データはtally状態が未確定のため通常fixtureから除外した（別途
# TestLegacyCompatibility.test_p66_pending_observation_* を参照）。
# 「旧帳票では店舗コード欄自体が存在しない」という契約上のふるまいは、
# P66の実データとは切り離し、合成payloadだけで単体テストする。
class TestOldFormStoreCodeNotApplicable:
    def test_old_form_store_code_not_applicable_is_a_normal_status(self):
        payload = _example_payload()
        payload["form_version"] = "old"
        payload["store_code"] = {
            "raw_value": None,
            "status": "not_applicable",
            "confidence": None,
            "notes": "旧帳票には店舗コード欄自体が存在しない（合成payloadによる契約レベルの単体テスト）",
        }
        page = _parse_example(payload, expected_form_version="old")
        assert page.store_code_evidence.status == EvidenceStatus.NOT_APPLICABLE
        assert page.store_code_evidence.raw_value is None
