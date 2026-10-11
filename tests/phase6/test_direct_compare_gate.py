"""FAX直接比較ゲートのテスト（店舗コードmaster照合・AUTO_MATCH判定・手入力再照合）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.phase6.direct_compare_gate import (
    AUTO_MATCH,
    NEEDS_REVIEW,
    apply_manual_override,
    decide_store_code,
    decide_written_total,
    load_valid_store_codes,
    normalize_store_code,
    validate_store_code,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data" / "phase6_received"
XLSX_FILES = [
    DATA_DIR / "SFAエクスポートマスター0625nn.xlsx",
    DATA_DIR / "SFAエクスポートマスター0626b.xlsx",
    DATA_DIR / "SFAエクスポートマスター0627b.xlsx",
]

needs_data = pytest.mark.skipif(
    not all(p.exists() for p in XLSX_FILES), reason="Phase 6 source Excel is not present (git-ignored)"
)


@pytest.fixture(scope="module")
def valid_codes():
    return load_valid_store_codes(XLSX_FILES)


# ---- normalize（固定regexなし。文字置換なし） ----

def test_normalize_strips_outer_and_inner_whitespace_and_uppercases():
    assert normalize_store_code("  AU1K C400079 ") == "AU1KC400079"
    assert normalize_store_code("AU1K　405 0055") == "AU1K4050055"
    assert normalize_store_code("au1k4050055") == "AU1K4050055"


def test_normalize_never_substitutes_look_alike_characters():
    assert normalize_store_code("AU1K433O093") == "AU1K433O093"  # O は 0 に置換しない
    assert normalize_store_code("AU1K433093") == "AU1K433093"    # 桁欠落も補完しない


# ---- master exact match ----

@needs_data
def test_master_contains_known_valid_codes(valid_codes):
    assert {"AU1K4050055", "AU1K4330093", "AU1KC400079"} <= valid_codes


@needs_data
def test_p41_whitespace_removed_is_exact_master_match(valid_codes):
    v = validate_store_code("AU1K C400079", valid_codes)
    assert v.exact_master_match is True
    assert v.normalized_value == "AU1KC400079"


@needs_data
@pytest.mark.parametrize(
    "raw, expected_candidate",
    [
        ("AU1K433O093", "AU1K4330093"),  # P32 AI（O 誤読）
        ("AU1K433093", "AU1K4330093"),  # P32 AI（桁欠落）
        ("AU1K405055", "AU1K4050055"),  # P59 AI（桁欠落）
    ],
)
def test_invalid_store_code_is_not_matched_and_only_suggested(valid_codes, raw, expected_candidate):
    v = validate_store_code(raw, valid_codes)
    assert v.exact_master_match is False
    assert v.normalized_value == raw.upper()  # 置換なし
    assert expected_candidate in v.candidates
    assert len(v.candidates) <= 3
    d = decide_store_code(validation=v, confidence="high", csv_store_code=expected_candidate)
    assert d.decision == NEEDS_REVIEW  # 候補が1件でも自動確定しない


@needs_data
def test_no_store_code_is_auto_matched_even_with_high_confidence(valid_codes):
    for raw in ["AU1K433O093", "AU1K433093", "AU1K405055", "AU1K405 0055"]:
        v = validate_store_code(raw, valid_codes)
        if v.exact_master_match:
            continue
        d = decide_store_code(validation=v, confidence="high", csv_store_code="AU1K4330093")
        assert d.decision == NEEDS_REVIEW, raw


# ---- written total: AUTO_MATCH条件 ----

def test_auto_match_only_when_observed_high_and_equal_to_csv():
    d = decide_written_total(
        item="intro", ai_value=2, ai_status="observed", confidence="high", csv_value=2, store_auto=True
    )
    assert d.decision == AUTO_MATCH


def test_written_total_never_auto_without_store_code_auto_match():
    d = decide_written_total(
        item="intro", ai_value=2, ai_status="observed", confidence="high", csv_value=2, store_auto=False
    )
    assert d.decision == NEEDS_REVIEW
    assert "store_code_not_auto" in d.reasons


@pytest.mark.parametrize(
    "kwargs, reason",
    [
        (dict(ai_value=0, ai_status="observed", confidence="medium", csv_value=0), "confidence_medium"),
        (dict(ai_value=None, ai_status="unreadable", confidence="low", csv_value=1), "ai_status_unreadable"),
        (dict(ai_value=None, ai_status="no_value", confidence="high", csv_value=0), "ai_status_no_value"),
        (dict(ai_value=3, ai_status="observed", confidence="high", csv_value=2), "ai_csv_mismatch"),
        (dict(ai_value=0, ai_status="observed", confidence="high", csv_value=0, csv_row_count=2), "csv_rows_2"),
    ],
)
def test_written_total_falls_back_to_needs_review(kwargs, reason):
    d = decide_written_total(item="voice", **kwargs)
    assert d.decision == NEEDS_REVIEW
    assert reason in d.reasons


def test_medium_confidence_equal_values_are_not_auto_matched():
    # 偶然一致しても medium なら AUTO_MATCH にしない（ルール5）
    d = decide_written_total(item="intro", ai_value=0, ai_status="observed", confidence="medium", csv_value=0)
    assert d.decision == NEEDS_REVIEW


# ---- manual override logic（人の確認を意味しない。手入力を受け付けて再照合するロジックのテスト） ----

def test_manual_override_logic_rematches_after_needs_review():
    first = decide_written_total(item="intro", ai_value=None, ai_status="unreadable", confidence="low", csv_value=1)
    assert first.decision == NEEDS_REVIEW
    second = apply_manual_override(item_name="intro", manual_value=1, csv_value=1)
    assert second.decision == "MANUAL_CONFIRMED_MATCH"


def test_manual_override_mismatch_stays_needs_review():
    result = apply_manual_override(item_name="intro", manual_value=2, csv_value=1)
    assert result.decision == NEEDS_REVIEW
    assert "manual_csv_mismatch" in result.reasons
