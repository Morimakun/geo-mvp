"""Step 2: evidence schema のテスト。

設計根拠: docs/PHASE_6_TRIPLE_EVIDENCE_SCHEMA_DESIGN_REVIEW.md 第4版

CSV照合・Vision抽出・三者比較には一切触れない（本モジュールのスコープ外）。
P41・P66については、確認できていない正の字の状態を推測でテストデータへ入れない
（ユーザー指示）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.phase6.evidence_schema import (  # noqa: E402
    CellRepresentation,
    Confidence,
    EvidenceStatus,
    EvidenceValidationError,
    NumericFieldEvidence,
    PageEvidence,
    StoreCodeEvidence,
    StoreCodeFormatStatus,
    TallyComponent,
    TallyEvidence,
    TallyObservationStatus,
    WrittenTotalEvidence,
)


def _observed(value: int) -> WrittenTotalEvidence:
    return WrittenTotalEvidence(value=value, status=EvidenceStatus.OBSERVED)


def _no_marks_tally() -> TallyEvidence:
    return TallyEvidence(observation_status=TallyObservationStatus.NO_MARKS_OBSERVED)


class TestTallyCountFormula:
    def test_complete_five_groups_1_plus_remainder_2_equals_7(self):
        tally = TallyEvidence(
            observation_status=TallyObservationStatus.MARKS_PRESENT,
            complete_five_groups=1,
            remainder_strokes=2,
        )
        assert tally.tally_count == 7

    def test_no_marks_observed_tally_count_is_none(self):
        tally = _no_marks_tally()
        assert tally.tally_count is None

    def test_no_marks_observed_is_not_coerced_to_zero(self):
        tally = _no_marks_tally()
        assert tally.complete_five_groups is None
        assert tally.remainder_strokes is None
        assert tally.tally_count is None


class TestTallyValidation:
    def test_unreadable_with_numeric_values_raises(self):
        with pytest.raises(EvidenceValidationError):
            TallyEvidence(
                observation_status=TallyObservationStatus.UNREADABLE,
                complete_five_groups=1,
                remainder_strokes=0,
            )

    def test_not_applicable_with_numeric_values_raises(self):
        with pytest.raises(EvidenceValidationError):
            TallyEvidence(
                observation_status=TallyObservationStatus.NOT_APPLICABLE,
                complete_five_groups=0,
                remainder_strokes=0,
            )

    def test_no_marks_observed_with_numeric_values_raises(self):
        with pytest.raises(EvidenceValidationError):
            TallyEvidence(
                observation_status=TallyObservationStatus.NO_MARKS_OBSERVED,
                complete_five_groups=0,
                remainder_strokes=0,
            )

    def test_remainder_strokes_5_or_more_raises(self):
        with pytest.raises(EvidenceValidationError):
            TallyEvidence(
                observation_status=TallyObservationStatus.MARKS_PRESENT,
                complete_five_groups=0,
                remainder_strokes=5,
            )

    def test_negative_complete_five_groups_raises(self):
        with pytest.raises(EvidenceValidationError):
            TallyEvidence(
                observation_status=TallyObservationStatus.MARKS_PRESENT,
                complete_five_groups=-1,
                remainder_strokes=0,
            )

    def test_negative_remainder_strokes_raises(self):
        with pytest.raises(EvidenceValidationError):
            TallyEvidence(
                observation_status=TallyObservationStatus.MARKS_PRESENT,
                complete_five_groups=0,
                remainder_strokes=-1,
            )

    def test_marks_present_requires_both_numeric_fields(self):
        with pytest.raises(EvidenceValidationError):
            TallyEvidence(
                observation_status=TallyObservationStatus.MARKS_PRESENT,
                complete_five_groups=1,
                remainder_strokes=None,
            )

    def test_component_negative_value_raises(self):
        with pytest.raises(EvidenceValidationError):
            TallyComponent(row_label="A", complete_five_groups=-1, remainder_strokes=0)

    def test_component_remainder_out_of_range_raises(self):
        with pytest.raises(EvidenceValidationError):
            TallyComponent(row_label="A", complete_five_groups=0, remainder_strokes=5)


class TestTallyComponentsSumConsistency:
    def test_component_sum_matches_aggregate_is_allowed(self):
        tally = TallyEvidence(
            observation_status=TallyObservationStatus.MARKS_PRESENT,
            complete_five_groups=1,
            remainder_strokes=2,
            components=[
                TallyComponent(row_label="A", complete_five_groups=1, remainder_strokes=0),
                TallyComponent(row_label="B", complete_five_groups=0, remainder_strokes=2),
            ],
        )
        assert tally.tally_count == 7
        assert sum(c.count for c in tally.components) == 7

    def test_component_sum_mismatch_raises(self):
        with pytest.raises(EvidenceValidationError):
            TallyEvidence(
                observation_status=TallyObservationStatus.MARKS_PRESENT,
                complete_five_groups=2,
                remainder_strokes=0,
                components=[
                    TallyComponent(row_label="A", complete_five_groups=1, remainder_strokes=0),
                ],
            )


class TestWrittenTotalValidation:
    def test_observed_without_value_raises(self):
        with pytest.raises(EvidenceValidationError):
            WrittenTotalEvidence(value=None, status=EvidenceStatus.OBSERVED)

    def test_no_value_with_value_raises(self):
        with pytest.raises(EvidenceValidationError):
            WrittenTotalEvidence(value=5, status=EvidenceStatus.NO_VALUE)

    def test_unreadable_with_value_raises(self):
        with pytest.raises(EvidenceValidationError):
            WrittenTotalEvidence(value=1, status=EvidenceStatus.UNREADABLE)

    def test_observed_with_value_is_allowed(self):
        evidence = WrittenTotalEvidence(value=7, status=EvidenceStatus.OBSERVED)
        assert evidence.value == 7

    def test_no_value_without_value_is_allowed(self):
        evidence = WrittenTotalEvidence(value=None, status=EvidenceStatus.NO_VALUE)
        assert evidence.value is None


def _make_page_evidence(
    *,
    page_no: int = 1,
    intro_value: int = 7,
    voice_value: int = 3,
    store_code: str = "AU1K000000",
) -> PageEvidence:
    return PageEvidence(
        page_no=page_no,
        form_version="new",
        selected_business_date="2026-06-27",
        store_code_evidence=StoreCodeEvidence(
            raw_value=store_code,
            normalized_value=store_code,
            status=EvidenceStatus.OBSERVED,
            format_status=StoreCodeFormatStatus.VALID,
        ),
        intro_evidence=NumericFieldEvidence(
            written_total=_observed(intro_value),
            tally=_no_marks_tally(),
        ),
        voice_evidence=NumericFieldEvidence(
            written_total=_observed(voice_value),
            tally=_no_marks_tally(),
        ),
    )


class TestIntroVoiceIndependence:
    def test_intro_and_voice_are_held_independently(self):
        page = _make_page_evidence(intro_value=7, voice_value=3)
        assert page.intro_evidence.written_total.value == 7
        assert page.voice_evidence.written_total.value == 3
        assert page.intro_evidence is not page.voice_evidence

    def test_intro_and_voice_can_differ_in_status(self):
        page = PageEvidence(
            page_no=1,
            form_version="new",
            selected_business_date="2026-06-27",
            store_code_evidence=StoreCodeEvidence(),
            intro_evidence=NumericFieldEvidence(
                written_total=_observed(7),
                tally=_no_marks_tally(),
            ),
            voice_evidence=NumericFieldEvidence(
                written_total=WrittenTotalEvidence(value=None, status=EvidenceStatus.NO_VALUE),
                tally=_no_marks_tally(),
            ),
        )
        assert page.intro_total == 7
        assert page.voice_callout_total is None


class TestLegacyDerivation:
    def test_legacy_fields_are_derived_from_source_of_truth(self):
        page = _make_page_evidence(intro_value=7, voice_value=3)
        assert page.intro_total == page.intro_evidence.written_total.value == 7
        assert page.voice_callout_total == page.voice_evidence.written_total.value == 3

    def test_to_dict_without_legacy_has_no_legacy_keys(self):
        page = _make_page_evidence()
        data = page.to_dict()
        assert "intro_total" not in data
        assert "voice_callout_total" not in data

    def test_to_dict_with_legacy_matches_source_of_truth(self):
        page = _make_page_evidence(intro_value=7, voice_value=3)
        data = page.to_dict(include_legacy=True)
        assert data["intro_total"] == 7
        assert data["voice_callout_total"] == 3
        assert data["intro_total"] == data["intro_evidence"]["written_total"]["value"]
        assert data["voice_callout_total"] == data["voice_evidence"]["written_total"]["value"]

    def test_from_legacy_dict_derives_source_of_truth(self):
        page = PageEvidence.from_legacy_dict(
            {
                "page_no": 1,
                "selected_business_date": "2026-06-27",
                "intro_total": 4,
                "voice_callout_total": 0,
            }
        )
        assert page.intro_total == 4
        assert page.voice_callout_total == 0
        assert page.intro_evidence.tally.observation_status == TallyObservationStatus.NOT_OBSERVED


class TestJsonSerialization:
    def test_page_evidence_is_json_serializable(self):
        page = _make_page_evidence()
        serialized = json.dumps(page.to_dict(include_legacy=True))
        restored = json.loads(serialized)
        assert restored["intro_total"] == page.intro_total
        assert restored["store_code_evidence"]["raw_value"] == page.store_code_evidence.raw_value

    def test_page_evidence_with_components_is_json_serializable(self):
        page = PageEvidence(
            page_no=1,
            form_version="new",
            selected_business_date="2026-06-27",
            store_code_evidence=StoreCodeEvidence(),
            intro_evidence=NumericFieldEvidence(
                written_total=_observed(7),
                tally=TallyEvidence(
                    observation_status=TallyObservationStatus.MARKS_PRESENT,
                    complete_five_groups=1,
                    remainder_strokes=2,
                    confidence=Confidence.HIGH,
                    components=[
                        TallyComponent(row_label="A", complete_five_groups=1, remainder_strokes=2),
                    ],
                ),
            ),
            voice_evidence=NumericFieldEvidence(
                written_total=_observed(3),
                tally=_no_marks_tally(),
            ),
        )
        serialized = json.dumps(page.to_dict(include_legacy=True))
        restored = json.loads(serialized)
        assert restored["intro_evidence"]["tally"]["tally_count"] == 7
        assert restored["intro_evidence"]["tally"]["components"][0]["count"] == 7
        assert restored["intro_evidence"]["tally"]["confidence"] == "high"


class TestRealDataP32StoreCodePreserved:
    def test_p32_store_code_is_held_as_is(self):
        evidence = StoreCodeEvidence(
            raw_value="4330093",
            normalized_value="4330093",
            status=EvidenceStatus.OBSERVED,
            format_status=StoreCodeFormatStatus.VALID,
        )
        page = PageEvidence(
            page_no=32,
            form_version="new",
            selected_business_date="2026-06-26",
            store_code_evidence=evidence,
            intro_evidence=NumericFieldEvidence(
                written_total=_observed(2),
                tally=_no_marks_tally(),
            ),
            voice_evidence=NumericFieldEvidence(
                written_total=_observed(0),
                tally=_no_marks_tally(),
            ),
        )
        assert page.store_code_evidence.raw_value == "4330093"
        assert page.store_code_evidence.normalized_value == "4330093"
        assert json.dumps(page.to_dict())  # JSONシリアライズ可能であることも確認


class TestRealDataP59WrittenTotalZero:
    def test_p59_written_total_zero_with_no_marks_observed(self):
        written_total = _observed(0)
        tally = _no_marks_tally()
        assert written_total.value == 0
        assert written_total.status == EvidenceStatus.OBSERVED
        assert tally.observation_status == TallyObservationStatus.NO_MARKS_OBSERVED
        assert tally.tally_count is None

        page = PageEvidence(
            page_no=59,
            form_version="new",
            selected_business_date="2026-06-25",
            store_code_evidence=StoreCodeEvidence(),
            intro_evidence=NumericFieldEvidence(written_total=written_total, tally=tally),
            voice_evidence=NumericFieldEvidence(written_total=_observed(0), tally=_no_marks_tally()),
        )
        assert page.intro_total == 0
        assert page.intro_evidence.tally.tally_count is None


class TestNotObservedStatus:
    def test_legacy_json_without_tally_info_is_not_observed_with_null_count(self):
        page = PageEvidence.from_legacy_dict(
            {
                "page_no": 1,
                "selected_business_date": "2026-06-27",
                "intro_total": 4,
                "voice_callout_total": 0,
            }
        )
        assert page.intro_evidence.tally.observation_status == TallyObservationStatus.NOT_OBSERVED
        assert page.intro_evidence.tally.tally_count is None
        assert page.voice_evidence.tally.observation_status == TallyObservationStatus.NOT_OBSERVED
        assert page.voice_evidence.tally.tally_count is None

    def test_legacy_json_without_store_code_key_is_not_observed(self):
        page = PageEvidence.from_legacy_dict(
            {
                "page_no": 1,
                "selected_business_date": "2026-06-27",
                "intro_total": 4,
                "voice_callout_total": 0,
            }
        )
        assert page.store_code_evidence.status == EvidenceStatus.NOT_OBSERVED
        assert page.store_code_evidence.raw_value is None

    def test_legacy_json_with_explicit_store_code_not_applicable_override(self):
        page = PageEvidence.from_legacy_dict(
            {
                "page_no": 1,
                "selected_business_date": "2026-06-27",
                "intro_total": 4,
                "voice_callout_total": 0,
                "store_code_status": "not_applicable",
            }
        )
        assert page.store_code_evidence.status == EvidenceStatus.NOT_APPLICABLE

    def test_legacy_json_with_key_present_and_none_value_is_no_value(self):
        page = PageEvidence.from_legacy_dict(
            {
                "page_no": 1,
                "selected_business_date": "2026-06-27",
                "intro_total": None,
                "voice_callout_total": 0,
                "store_code": None,
            }
        )
        assert page.intro_evidence.written_total.status == EvidenceStatus.NO_VALUE
        assert page.store_code_evidence.status == EvidenceStatus.NO_VALUE

    def test_no_value_and_not_observed_serialize_to_different_json_values(self):
        no_value = StoreCodeEvidence(status=EvidenceStatus.NO_VALUE)
        not_observed = StoreCodeEvidence(status=EvidenceStatus.NOT_OBSERVED)
        assert no_value.to_dict()["status"] == "no_value"
        assert not_observed.to_dict()["status"] == "not_observed"
        assert no_value.to_dict()["status"] != not_observed.to_dict()["status"]

    def test_not_observed_tally_with_numeric_values_raises(self):
        with pytest.raises(EvidenceValidationError):
            TallyEvidence(
                observation_status=TallyObservationStatus.NOT_OBSERVED,
                complete_five_groups=1,
                remainder_strokes=0,
            )

    def test_not_observed_written_total_with_value_raises(self):
        with pytest.raises(EvidenceValidationError):
            WrittenTotalEvidence(value=5, status=EvidenceStatus.NOT_OBSERVED)


# ============================================================
# Step 3B v3: cell_representation（合成データのみ。実PDF・Excel・Vision APIは使わない）
# ============================================================
def _marks_present_tally(count: int) -> TallyEvidence:
    return TallyEvidence(
        observation_status=TallyObservationStatus.MARKS_PRESENT,
        complete_five_groups=count // 5,
        remainder_strokes=count % 5,
    )


def _unreadable_written() -> WrittenTotalEvidence:
    return WrittenTotalEvidence(value=None, status=EvidenceStatus.UNREADABLE)


def _unreadable_tally() -> TallyEvidence:
    return TallyEvidence(observation_status=TallyObservationStatus.UNREADABLE)


def _no_value_written() -> WrittenTotalEvidence:
    return WrittenTotalEvidence(value=None, status=EvidenceStatus.NO_VALUE)


class TestCellRepresentationNumeric:
    def test_numeric_with_positive_value_is_accepted(self):
        field = NumericFieldEvidence(
            written_total=_observed(3),
            tally=_no_marks_tally(),
            cell_representation=CellRepresentation.NUMERIC,
        )
        assert field.cell_representation == CellRepresentation.NUMERIC

    def test_numeric_zero_is_preserved_as_valid_value_not_treated_as_missing(self):
        field = NumericFieldEvidence(
            written_total=_observed(0),
            tally=_no_marks_tally(),
            cell_representation=CellRepresentation.NUMERIC,
        )
        assert field.written_total.value == 0
        assert field.written_total.status == EvidenceStatus.OBSERVED
        assert field.to_dict()["written_total"]["value"] == 0
        assert field.to_dict()["cell_representation"] == "numeric"

    def test_numeric_requires_written_total_observed(self):
        with pytest.raises(EvidenceValidationError):
            NumericFieldEvidence(
                written_total=_no_value_written(),
                tally=_no_marks_tally(),
                cell_representation=CellRepresentation.NUMERIC,
            )

    def test_numeric_rejects_tally_marks_present(self):
        with pytest.raises(EvidenceValidationError):
            NumericFieldEvidence(
                written_total=_observed(3),
                tally=_marks_present_tally(3),
                cell_representation=CellRepresentation.NUMERIC,
            )


class TestCellRepresentationTally:
    def test_tally_with_marks_present_is_accepted(self):
        field = NumericFieldEvidence(
            written_total=_no_value_written(),
            tally=_marks_present_tally(7),
            cell_representation=CellRepresentation.TALLY,
        )
        assert field.cell_representation == CellRepresentation.TALLY
        assert field.tally.tally_count == 7

    def test_tally_requires_written_total_no_value(self):
        with pytest.raises(EvidenceValidationError):
            NumericFieldEvidence(
                written_total=_observed(3),
                tally=_marks_present_tally(3),
                cell_representation=CellRepresentation.TALLY,
            )

    def test_tally_requires_marks_present_not_no_marks_observed(self):
        with pytest.raises(EvidenceValidationError):
            NumericFieldEvidence(
                written_total=_no_value_written(),
                tally=_no_marks_tally(),
                cell_representation=CellRepresentation.TALLY,
            )


class TestCellRepresentationBlank:
    def test_blank_is_accepted(self):
        field = NumericFieldEvidence(
            written_total=_no_value_written(),
            tally=_no_marks_tally(),
            cell_representation=CellRepresentation.BLANK,
        )
        assert field.cell_representation == CellRepresentation.BLANK
        assert field.written_total.value is None
        assert field.tally.tally_count is None

    def test_blank_rejects_observed_written_total(self):
        with pytest.raises(EvidenceValidationError):
            NumericFieldEvidence(
                written_total=_observed(0),
                tally=_no_marks_tally(),
                cell_representation=CellRepresentation.BLANK,
            )


class TestCellRepresentationUnreadable:
    def test_unreadable_is_accepted(self):
        field = NumericFieldEvidence(
            written_total=_unreadable_written(),
            tally=_unreadable_tally(),
            cell_representation=CellRepresentation.UNREADABLE,
        )
        assert field.cell_representation == CellRepresentation.UNREADABLE

    def test_unreadable_written_with_marks_present_tally_is_rejected(self):
        """P32 v2で実際に発生した written=unreadable + tally=marks_present の組み合わせ。
        5パターンのいずれにも一致しないため必ず拒否されること。"""
        with pytest.raises(EvidenceValidationError):
            NumericFieldEvidence(
                written_total=_unreadable_written(),
                tally=_marks_present_tally(3),
                cell_representation=CellRepresentation.UNREADABLE,
            )

    def test_unreadable_requires_tally_also_unreadable_not_no_marks_observed(self):
        with pytest.raises(EvidenceValidationError):
            NumericFieldEvidence(
                written_total=_unreadable_written(),
                tally=_no_marks_tally(),
                cell_representation=CellRepresentation.UNREADABLE,
            )


class TestCellRepresentationMixed:
    def test_mixed_requires_both_written_and_tally_evidence_present(self):
        field = NumericFieldEvidence(
            written_total=_observed(5),
            tally=_marks_present_tally(3),
            cell_representation=CellRepresentation.MIXED,
        )
        assert field.cell_representation == CellRepresentation.MIXED
        # mixedは後段で必ず要確認にできるよう、両方の実測値を保持していること。
        assert field.written_total.value == 5
        assert field.tally.tally_count == 3

    def test_mixed_rejects_written_total_not_observed(self):
        with pytest.raises(EvidenceValidationError):
            NumericFieldEvidence(
                written_total=_no_value_written(),
                tally=_marks_present_tally(3),
                cell_representation=CellRepresentation.MIXED,
            )

    def test_mixed_rejects_tally_not_marks_present(self):
        with pytest.raises(EvidenceValidationError):
            NumericFieldEvidence(
                written_total=_observed(5),
                tally=_no_marks_tally(),
                cell_representation=CellRepresentation.MIXED,
            )


class TestCellRepresentationBackwardCompatibility:
    def test_none_is_allowed_for_legacy_data_and_skips_validation(self):
        # 旧JSON・旧処理からの移行データとの互換性のため、書かれている内容が
        # 5パターンのどれにも一致しなくてもcell_representation=Noneなら検証をスキップする。
        field = NumericFieldEvidence(
            written_total=_unreadable_written(),
            tally=_marks_present_tally(3),
        )
        assert field.cell_representation is None

    def test_from_legacy_dict_leaves_cell_representation_none(self):
        page = PageEvidence.from_legacy_dict(
            {
                "page_no": 1,
                "selected_business_date": "2026-06-27",
                "intro_total": 4,
                "voice_callout_total": 0,
            }
        )
        assert page.intro_evidence.cell_representation is None
        assert page.voice_evidence.cell_representation is None

    def test_to_dict_serializes_none_cell_representation_as_null(self):
        field = NumericFieldEvidence(written_total=_observed(3), tally=_no_marks_tally())
        assert field.to_dict()["cell_representation"] is None
