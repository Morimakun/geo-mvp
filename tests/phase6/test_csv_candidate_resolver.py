"""Step 1: CSV candidate resolver のテスト。

設計根拠: docs/PHASE_6_TRIPLE_EVIDENCE_SCHEMA_DESIGN_REVIEW.md 第4版

- 実データ統合テスト（P23/P32/P41/P59/P66）: data/phase6_received/ の実際のSalesforce
  エクスポートファイルを直接読み込み、設計書に明記された期待結果と突合する。
- 単体テスト: openpyxlで合成した一時ワークブックを使い、境界条件・異常系を検証する。

Vision抽出・正の字読取り・三者照合には一切触れない（本モジュールのスコープ外）。

命名注意: csv_review_required/csv_review_reasons はCSV結合工程単体の結果であり、
ページ全体のreview_requiredではない（本ファイルのテストでもこの区別を明示する）。
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import openpyxl
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.phase6.csv_candidate_resolver import (  # noqa: E402
    COLUMN_DATE,
    COLUMN_INTRO_TOTAL,
    COLUMN_STORE_CODE,
    COLUMN_VOICE_CALLOUT_TOTAL,
    RESOLUTION_BASIS_UNVERIFIED_REFERENCE,
    CsvMatchStatus,
    CsvResolverInput,
    CsvSheetNotFoundError,
    CsvSourceNotFoundError,
    InvalidBusinessDateError,
    InvalidResolutionRuleError,
    StoreCodeResolutionSource,
    _excel_serial_to_date,  # noqa: PLC2701 - 内部ヘルパーの単体テストのため直接importする
    _to_optional_int,
    resolve_csv_candidates,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RECEIVED_DIR = REPO_ROOT / "data" / "phase6_received"
FILE_0625 = RECEIVED_DIR / "SFAエクスポートマスター0625nn.xlsx"
FILE_0626 = RECEIVED_DIR / "SFAエクスポートマスター0626b.xlsx"
FILE_0627 = RECEIVED_DIR / "SFAエクスポートマスター0627b.xlsx"

pytestmark = pytest.mark.skipif(
    not (FILE_0625.exists() and FILE_0626.exists() and FILE_0627.exists()),
    reason="data/phase6_received/ のSalesforceエクスポートファイルが見つかりません",
)


# ============================================================
# 実データ統合テスト（設計書10節の証跡と突合）
# ============================================================
class TestRealDataP23MultipleUnresolved:
    """P23（ニトリモール枚方, 2026-06-27, AU1KW740165）: 同一店舗コード・同一営業日で
    CSV候補2行 -> multiple_unresolved。"""

    def test_p23_multiple_unresolved(self):
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(FILE_0627),
                sheet_name="CSV",
                selected_business_date="2026-06-27",
                store_code="AU1KW740165",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.MULTIPLE_UNRESOLVED
        assert result.resolved_candidate_row is None
        assert result.csv_review_required is True
        assert "csv_multiple_unresolved" in result.csv_review_reasons
        assert len(result.csv_candidate_rows) == 2

        row_numbers = sorted(r.row_number for r in result.csv_candidate_rows)
        assert row_numbers == [26, 27]

        by_row = {r.row_number: r for r in result.csv_candidate_rows}
        assert by_row[26].intro_total == 6
        assert by_row[27].intro_total == 5
        assert all(r.voice_callout_total == 0 for r in result.csv_candidate_rows)
        # 任意の先頭行を採用していないこと
        assert result.resolved_candidate_row is None


class TestRealDataP32NearMatch:
    """P32（布施, 2026-06-26, AI抽出コード AU1K430093）: exact matchは0件、
    近似候補としてAU1K4330093（編集距離1、連続する3の1桁欠落）を検出。自動確定はしない。"""

    def test_p32_not_found_with_near_match(self):
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(FILE_0626),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K430093",  # AIの誤読(1桁欠落)コードをそのままJOINキーに使う
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.NOT_FOUND
        assert result.resolved_candidate_row is None
        assert result.csv_review_required is True
        assert "csv_not_found" in result.csv_review_reasons
        assert "near_match_available_not_auto_confirmed" in result.csv_review_reasons

        assert len(result.near_match_candidates) >= 1
        near = next(
            (c for c in result.near_match_candidates if c.candidate_store_code == "AU1K4330093"),
            None,
        )
        assert near is not None, "近似候補にAU1K4330093が含まれていること"
        assert near.edit_distance == 1
        assert near.row_number == 10
        assert near.intro_total == 1
        assert near.voice_callout_total == 0
        assert "連続する3の1桁欠落候補" == near.difference_summary

        # 近似一致だけで自動確定していないこと(resolved_candidate_rowが常にNone)
        assert result.resolved_candidate_row is None
        assert result.csv_match_status != CsvMatchStatus.UNIQUE_MATCH
        assert result.csv_match_status != CsvMatchStatus.RESOLVED_BY_RULE


class TestRealDataP41UniqueMatch:
    """P41（広畑, 2026-06-26, AU1KC400079）: selected_business_dateで正しい候補を1件取得。"""

    def test_p41_unique_match(self):
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(FILE_0626),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1KC400079",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.UNIQUE_MATCH
        assert result.csv_review_required is False
        assert len(result.csv_candidate_rows) == 1
        assert result.resolved_candidate_row is not None
        assert result.resolved_candidate_row.row_number == 15
        assert result.resolved_candidate_row.intro_total == 2
        assert result.resolved_candidate_row.voice_callout_total == 0


class TestRealDataP59IndependentOfAi:
    """P59（ららぽーとEXPOCITY, 2026-06-25, AU1K4050055）: AI候補値とは独立してCSV候補を取得する。
    resolver内では三者比較を一切行わない。

    重要: csv_review_required=False はこのCSV結合工程単体の結果であり、
    ページ全体のreview_required（written_total・tally_countとの三者比較を経た結果）
    とは別物であることをここで明示的に確認する。
    """

    def test_p59_csv_lookup_independent_of_ai_candidate(self):
        # 意図的にAI候補(6)を一切参照せず、店舗コードだけをキーにする
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(FILE_0625),
                sheet_name="CSV",
                selected_business_date="2026-06-25",
                store_code="AU1K4050055",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.UNIQUE_MATCH
        assert result.resolved_candidate_row.row_number == 5
        assert result.resolved_candidate_row.intro_total == 0
        assert result.resolved_candidate_row.voice_callout_total == 0

        # CSV結合単体としてはreview不要、という結果
        assert result.csv_review_required is False
        assert result.csv_review_reasons == []

        # ↓これはページ全体のreview_requiredではないことのテスト上の裏付け:
        # resolverの出力型には三者比較用フィールドが一切存在しない
        # (written_total・ai_value・tally_count等はここでは扱えない -> 別モジュールの責務)
        result_fields = set(result.__dataclass_fields__)
        forbidden = {
            "written_total_value",
            "ai_value",
            "human_value",
            "tally_count",
            "evidence_comparison_result",
            "review_required",  # ページ全体用の名前をこのモジュールが名乗ってはいけない
            "review_reasons",
        }
        assert result_fields.isdisjoint(forbidden), (
            "resolverはCSV結合単体のcsv_review_required/csv_review_reasonsのみを持ち、"
            "ページ全体のreview_required/reviewreasonsという名前のフィールドを持たない"
        )


class TestRealDataP66ReferenceMatchUnverified:
    """P66（守口南寺方, 旧帳票, 2026-06-25）: 店舗コードがAI抽出店舗名＋未確認参考マスター経由で
    解決されたため、候補が1件でもunique_matchに昇格せずreference_match_unverifiedとする。"""

    def test_p66_reference_match_unverified(self):
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(FILE_0625),
                sheet_name="CSV",
                selected_business_date="2026-06-25",
                store_code="AU1KW740082",  # 呼び出し側が「入力マスター」経由で事前に解決した値
                store_code_resolution_source=StoreCodeResolutionSource.UNVERIFIED_REFERENCE,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.REFERENCE_MATCH_UNVERIFIED
        assert result.resolved_candidate_row is None
        assert result.csv_review_required is True
        assert result.resolution_basis == RESOLUTION_BASIS_UNVERIFIED_REFERENCE
        assert result.resolution_basis == "ai_store_name_plus_unverified_reference_master"

        # 候補行は参考表示のみ保持(三者一致には使わない = resolved_candidate_rowがNoneであることで担保)
        assert len(result.csv_candidate_rows) == 1
        assert result.csv_candidate_rows[0].row_number == 18
        assert result.csv_candidate_rows[0].intro_total == 6


# ============================================================
# 単体テスト（合成ワークブック）
# ============================================================
def _write_workbook(path: Path, rows: list[dict], sheet_name: str = "CSV") -> None:
    """テスト用の最小ワークブックを作成する。列位置は本番と同じcol1/36/105/283を使う。"""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name
    ws.cell(row=1, column=COLUMN_STORE_CODE, value="法人・店舗(取扱コード)")
    ws.cell(row=1, column=COLUMN_INTRO_TOTAL, value="紹介総数")
    ws.cell(row=1, column=COLUMN_VOICE_CALLOUT_TOTAL, value="お声がけ総数")
    ws.cell(row=1, column=COLUMN_DATE, value="日付")
    for i, r in enumerate(rows, start=2):
        ws.cell(row=i, column=COLUMN_STORE_CODE, value=r.get("store_code"))
        ws.cell(row=i, column=COLUMN_INTRO_TOTAL, value=r.get("intro_total"))
        ws.cell(row=i, column=COLUMN_VOICE_CALLOUT_TOTAL, value=r.get("voice_callout_total"))
        ws.cell(row=i, column=COLUMN_DATE, value=r.get("business_date"))
    wb.save(path)


# 2026-06-26のExcelシリアル値(本番ファイルで実際に確認した値と同じ変換規則)
SERIAL_20260626 = 46199
SERIAL_20260627 = 46200


class TestDateNormalization:
    def test_excel_serial_int(self):
        assert _excel_serial_to_date(SERIAL_20260626).isoformat() == "2026-06-26"

    def test_excel_serial_float(self):
        assert _excel_serial_to_date(float(SERIAL_20260626)).isoformat() == "2026-06-26"

    def test_iso_string(self):
        assert _excel_serial_to_date("2026-06-26").isoformat() == "2026-06-26"

    def test_slash_string(self):
        assert _excel_serial_to_date("2026/06/26").isoformat() == "2026-06-26"

    def test_compact_string(self):
        assert _excel_serial_to_date("20260626").isoformat() == "2026-06-26"

    def test_datetime_object(self):
        import datetime

        assert _excel_serial_to_date(datetime.datetime(2026, 6, 26)).isoformat() == "2026-06-26"

    def test_none_returns_none(self):
        assert _excel_serial_to_date(None) is None

    def test_unparseable_string_returns_none(self):
        assert _excel_serial_to_date("not a date") is None


class TestBlankCsvNotConvertedToZero:
    def test_none_stays_none(self):
        assert _to_optional_int(None) is None

    def test_empty_string_stays_none(self):
        assert _to_optional_int("") is None
        assert _to_optional_int("   ") is None

    def test_real_zero_is_preserved_as_zero(self):
        # 空欄(None)と実際の0は区別する。0が誤ってNoneになってはいけない。
        assert _to_optional_int(0) == 0
        assert _to_optional_int("0") == 0


class TestStrictNumericConversion:
    """_to_optional_int の厳格化仕様（レビュー指摘1点目）。
    不正値は0へフォールバックしない。すべてNoneとして「欠損」扱いする。"""

    def test_bool_true_is_not_converted_to_one(self):
        assert _to_optional_int(True) is None

    def test_bool_false_is_not_converted_to_zero(self):
        assert _to_optional_int(False) is None

    def test_plain_int_allowed(self):
        assert _to_optional_int(2) == 2
        assert _to_optional_int(-3) == -3
        assert _to_optional_int(0) == 0

    def test_float_with_fractional_part_1_9_is_none(self):
        # 1.9はintegerでないため許可しない(1へ切り捨てない)
        assert _to_optional_int(1.9) is None

    def test_float_2_5_is_none(self):
        assert _to_optional_int(2.5) is None

    def test_float_2_0_is_two(self):
        assert _to_optional_int(2.0) == 2

    def test_integer_string_is_allowed(self):
        assert _to_optional_int("2") == 2
        assert _to_optional_int("-5") == -5
        assert _to_optional_int("  7  ") == 7  # 前後空白は許容(trim後に整数形式)

    def test_decimal_string_2_0_is_rejected(self):
        # 仕様として明示: 小数点を含む文字列("2.0"含む)は「整数形式」ではないため拒否する。
        # (数値としては整数と等価でも、文字列としては小数形式なのでNoneとする)
        assert _to_optional_int("2.0") is None

    def test_nan_float_is_none(self):
        assert _to_optional_int(float("nan")) is None

    def test_infinity_float_is_none(self):
        assert _to_optional_int(float("inf")) is None
        assert _to_optional_int(float("-inf")) is None

    def test_nan_like_strings_are_none(self):
        assert _to_optional_int("nan") is None
        assert _to_optional_int("NaN") is None
        assert _to_optional_int("Infinity") is None
        assert _to_optional_int("inf") is None

    def test_mixed_character_string_is_none(self):
        assert _to_optional_int("12a") is None
        assert _to_optional_int("a12") is None
        assert _to_optional_int("１２") is None  # 全角数字も対象外(整数形式の厳密なASCII一致のみ許可)

    def test_invalid_value_is_never_converted_to_zero(self):
        for bad in (True, False, 2.5, "2.0", "abc", float("nan"), float("inf"), "１２"):
            assert _to_optional_int(bad) != 0
            assert _to_optional_int(bad) is None

    def test_invalid_value_is_recorded_in_notes_with_column_and_row(self):
        notes: list = []
        result = _to_optional_int(2.5, column_name="紹介総数(col36)", row_number=42, notes=notes)
        assert result is None
        assert len(notes) == 1
        assert "行42" in notes[0]
        assert "紹介総数(col36)" in notes[0]

    def test_notes_do_not_dump_large_raw_value(self):
        """セル値全体を無制限にログへ出さない(長い値は切り詰められる)。"""
        notes: list = []
        long_bad_value = "x" * 500
        _to_optional_int(long_bad_value, column_name="col36", row_number=1, notes=notes)
        assert len(notes) == 1
        assert len(notes[0]) < 200  # ノート全体が長大化していないこと

    def test_valid_value_does_not_add_note(self):
        notes: list = []
        result = _to_optional_int(5, column_name="col36", row_number=1, notes=notes)
        assert result == 5
        assert notes == []

    def test_none_value_does_not_add_note(self):
        """空欄(None)自体は不正値ではない(欠損として正常)ため、notesに記録しない。"""
        notes: list = []
        result = _to_optional_int(None, column_name="col36", row_number=1, notes=notes)
        assert result is None
        assert notes == []


class TestCandidateCountBranches:
    def test_zero_candidates_and_no_near_match(self, tmp_path):
        path = tmp_path / "zero.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1KZZZZZZZ", "intro_total": 1, "voice_callout_total": 0, "business_date": SERIAL_20260626},
            ],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K0000000",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.NOT_FOUND
        assert result.resolved_candidate_row is None
        assert result.csv_review_required is True

    def test_one_candidate_unique_match(self, tmp_path):
        path = tmp_path / "one.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.UNIQUE_MATCH
        assert result.resolved_candidate_row.intro_total == 3
        assert result.resolved_candidate_row.voice_callout_total == 1
        assert result.csv_review_required is False

    def test_multiple_candidates_multiple_unresolved(self, tmp_path):
        path = tmp_path / "multi.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},
                {"store_code": "AU1K1234567", "intro_total": 5, "voice_callout_total": 0, "business_date": SERIAL_20260626},
            ],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.MULTIPLE_UNRESOLVED
        assert result.resolved_candidate_row is None
        assert len(result.csv_candidate_rows) == 2
        assert result.csv_review_required is True

    def test_duplicate_rows_with_identical_values_still_multiple_unresolved(self, tmp_path):
        """値が完全に同じ2行であっても、行が2件ある以上multiple_unresolvedとする
        （値が同じだから安全に1件扱いしてよい、という近道はしない）。"""
        path = tmp_path / "dup_same_value.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},
                {"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},
            ],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.MULTIPLE_UNRESOLVED
        assert result.resolved_candidate_row is None
        assert len(result.csv_candidate_rows) == 2

    def test_single_candidate_with_blank_intro_total(self, tmp_path):
        path = tmp_path / "blank_intro.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234567", "intro_total": None, "voice_callout_total": 2, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.UNIQUE_MATCH
        assert result.resolved_candidate_row.intro_total is None  # 0へ変換されていないこと
        assert result.resolved_candidate_row.voice_callout_total == 2


class TestCsvEvidenceCompleteness:
    """レビュー指摘2点目: 店舗コードの一意解決(csv_match_status)と、
    数値の完全性(csv_review_required)は別軸として分離する。
    候補行が1件でunique_matchになっても、intro_total/voice_callout_totalの
    いずれかが欠損していればcsv_review_required=Trueとし、理由を積む。
    両方揃っている場合だけCSV証拠を完全とみなす。"""

    def test_intro_only_blank_sets_review_required_with_reason(self, tmp_path):
        path = tmp_path / "intro_blank.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234567", "intro_total": None, "voice_callout_total": 2, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.UNIQUE_MATCH  # 店舗コードは一意
        assert result.resolved_candidate_row is not None
        assert result.csv_review_required is True  # だが数値が不完全
        assert result.csv_review_reasons == ["intro_total_missing"]

    def test_voice_only_blank_sets_review_required_with_reason(self, tmp_path):
        path = tmp_path / "voice_blank.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234567", "intro_total": 4, "voice_callout_total": None, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.UNIQUE_MATCH
        assert result.resolved_candidate_row is not None
        assert result.csv_review_required is True
        assert result.csv_review_reasons == ["voice_callout_total_missing"]

    def test_both_blank_sets_review_required_with_both_reasons(self, tmp_path):
        path = tmp_path / "both_blank.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234567", "intro_total": None, "voice_callout_total": None, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.UNIQUE_MATCH
        assert result.csv_review_required is True
        assert set(result.csv_review_reasons) == {"intro_total_missing", "voice_callout_total_missing"}

    def test_zero_value_is_not_treated_as_missing(self, tmp_path):
        """値0は欠損ではない。intro=0, voice=0でもcsv_review_required=Falseのまま
        (CSV証拠は完全)であることを確認する。実データP41/P59もこのケースに該当する。"""
        path = tmp_path / "zero_values.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234567", "intro_total": 0, "voice_callout_total": 0, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.UNIQUE_MATCH
        assert result.resolved_candidate_row.intro_total == 0
        assert result.resolved_candidate_row.voice_callout_total == 0
        assert result.csv_review_required is False
        assert result.csv_review_reasons == []

    def test_both_present_means_csv_evidence_complete(self, tmp_path):
        path = tmp_path / "complete.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_review_required is False
        assert result.csv_review_reasons == []


class TestNearMatchCandidates:
    def test_multiple_near_matches_sorted_by_distance(self, tmp_path):
        path = tmp_path / "near.xlsx"
        _write_workbook(
            path,
            [
                # input="AU1K1234567" との編集距離: それぞれ 1, 2 になるよう構成
                {"store_code": "AU1K1234568", "intro_total": 1, "voice_callout_total": 0, "business_date": SERIAL_20260626},  # 距離1(末尾置換)
                {"store_code": "AU1K1234500", "intro_total": 2, "voice_callout_total": 0, "business_date": SERIAL_20260626},  # 距離2
            ],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
                near_match_edit_distance_threshold=2,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.NOT_FOUND
        assert result.resolved_candidate_row is None
        assert len(result.near_match_candidates) == 2
        distances = [c.edit_distance for c in result.near_match_candidates]
        assert distances == sorted(distances)  # 昇順であること
        assert distances[0] == 1

    def test_candidates_beyond_threshold_excluded(self, tmp_path):
        path = tmp_path / "far.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1234568", "intro_total": 1, "voice_callout_total": 0, "business_date": SERIAL_20260626},  # 距離1: 含む
                {"store_code": "ZZZZZZZZZZZ", "intro_total": 9, "voice_callout_total": 0, "business_date": SERIAL_20260626},  # 距離大: 除外
            ],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
                near_match_edit_distance_threshold=1,
            )
        )
        codes = [c.candidate_store_code for c in result.near_match_candidates]
        assert "AU1K1234568" in codes
        assert "ZZZZZZZZZZZ" not in codes

    def test_single_near_match_still_leaves_resolved_row_null(self, tmp_path):
        """近似候補が1件しかなくても、resolved_candidate_rowはnullのままとする
        （近似一致は自動解決の対象にしない）。"""
        path = tmp_path / "single_near.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234568", "intro_total": 1, "voice_callout_total": 0, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.NOT_FOUND
        assert len(result.near_match_candidates) == 1
        assert result.resolved_candidate_row is None


class TestRowNumberAndDataRowIndex:
    def test_row_number_is_excel_1indexed_with_header(self, tmp_path):
        path = tmp_path / "rows.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1111111", "intro_total": 1, "voice_callout_total": 0, "business_date": SERIAL_20260626},
                {"store_code": "AU1K2222222", "intro_total": 2, "voice_callout_total": 0, "business_date": SERIAL_20260626},
            ],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K2222222",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        row = result.csv_candidate_rows[0]
        # ヘッダーが1行目、1件目のデータが2行目、2件目のデータが3行目
        assert row.row_number == 3
        assert row.data_row_index == 1  # ヘッダーを除いた0始まり連番


class TestMissingDataRowsDoNotCrash:
    def test_missing_store_code_and_unparseable_date_are_skipped_not_raised(self, tmp_path):
        path = tmp_path / "messy.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": None, "intro_total": 1, "voice_callout_total": 0, "business_date": SERIAL_20260626},  # 店舗コード欠損
                {"store_code": "AU1K3333333", "intro_total": 2, "voice_callout_total": 0, "business_date": "not a date"},  # 日付不能
                {"store_code": "AU1K4444444", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},  # 正常行
            ],
        )
        # 例外を送出せず正常終了すること
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K4444444",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.UNIQUE_MATCH
        assert len(result.data_quality_notes) == 2  # 店舗コード欠損行・日付不能行の2件が記録される


class TestStructuredErrors:
    def test_missing_source_file_raises_typed_error(self):
        with pytest.raises(CsvSourceNotFoundError):
            resolve_csv_candidates(
                CsvResolverInput(
                    source_file="does_not_exist.xlsx",
                    sheet_name="CSV",
                    selected_business_date="2026-06-26",
                    store_code="AU1K1234567",
                )
            )

    def test_missing_sheet_raises_typed_error(self, tmp_path):
        path = tmp_path / "empty.xlsx"
        _write_workbook(path, [])
        with pytest.raises(CsvSheetNotFoundError):
            resolve_csv_candidates(
                CsvResolverInput(
                    source_file=str(path),
                    sheet_name="存在しないシート",
                    selected_business_date="2026-06-26",
                    store_code="AU1K1234567",
                )
            )

    def test_invalid_business_date_raises_typed_error(self, tmp_path):
        path = tmp_path / "empty2.xlsx"
        _write_workbook(path, [])
        with pytest.raises(InvalidBusinessDateError):
            resolve_csv_candidates(
                CsvResolverInput(
                    source_file=str(path),
                    sheet_name="CSV",
                    selected_business_date="2026年6月26日",  # ISO形式でない
                    store_code="AU1K1234567",
                )
            )


class TestStoreCodeResolutionSourceGating:
    """unique_matchへ昇格してよいのはDIRECT_FORM_READのみ。候補1件でも
    UNVERIFIED_REFERENCE / UNKNOWN では昇格させない。"""

    def test_unverified_reference_with_one_candidate_is_reference_match_unverified(self, tmp_path):
        path = tmp_path / "unverified.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234567", "intro_total": 1, "voice_callout_total": 0, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.UNVERIFIED_REFERENCE,
            )
        )
        assert result.csv_match_status == CsvMatchStatus.REFERENCE_MATCH_UNVERIFIED
        assert result.resolved_candidate_row is None
        assert result.csv_review_required is True
        assert result.resolution_basis == RESOLUTION_BASIS_UNVERIFIED_REFERENCE

    def test_unknown_source_with_one_candidate_does_not_auto_confirm(self, tmp_path):
        path = tmp_path / "unknown_source.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234567", "intro_total": 1, "voice_callout_total": 0, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.UNKNOWN,
            )
        )
        # 情報源が未指定の場合は安全側に倒し、unique_matchへ昇格させない
        assert result.csv_match_status == CsvMatchStatus.REFERENCE_MATCH_UNVERIFIED
        assert result.resolved_candidate_row is None


class TestResolvedByRuleSafety:
    """resolved_by_ruleは監査可能な根拠(resolution_rule_basis)・識別子(resolution_rule_id)
    なしには成立しない。business_mode_hintだけを渡しても自動でresolved_by_ruleにはならない。
    ルールがexact_matches外の値を返した場合はInvalidResolutionRuleError。
    2026-07-20時点で先方確認済みの機械判別ルールは存在しないため、実運用でresolution_ruleを
    渡す呼び出しは無く、P23は常にmultiple_unresolvedのままとなる（実データテスト側で確認済み）。"""

    def test_resolution_rule_without_basis_raises(self, tmp_path):
        path = tmp_path / "rule_no_basis.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},
                {"store_code": "AU1K1234567", "intro_total": 5, "voice_callout_total": 0, "business_date": SERIAL_20260626},
            ],
        )

        def pick_first(candidates):
            return candidates[0]

        with pytest.raises(InvalidResolutionRuleError):
            resolve_csv_candidates(
                CsvResolverInput(
                    source_file=str(path),
                    sheet_name="CSV",
                    selected_business_date="2026-06-26",
                    store_code="AU1K1234567",
                    store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
                    resolution_rule=pick_first,
                    resolution_rule_basis=None,  # 根拠なし -> エラーになるべき
                    resolution_rule_id="test.pick_first",
                )
            )

    def test_resolution_rule_without_id_raises(self, tmp_path):
        path = tmp_path / "rule_no_id.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},
                {"store_code": "AU1K1234567", "intro_total": 5, "voice_callout_total": 0, "business_date": SERIAL_20260626},
            ],
        )

        def pick_first(candidates):
            return candidates[0]

        with pytest.raises(InvalidResolutionRuleError):
            resolve_csv_candidates(
                CsvResolverInput(
                    source_file=str(path),
                    sheet_name="CSV",
                    selected_business_date="2026-06-26",
                    store_code="AU1K1234567",
                    store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
                    resolution_rule=pick_first,
                    resolution_rule_basis="テスト用ルール",
                    resolution_rule_id=None,  # 識別子なし -> エラーになるべき
                )
            )

    def test_business_mode_hint_alone_does_not_trigger_resolved_by_rule(self, tmp_path):
        """resolution_ruleを指定しない限り、business_mode_hintを渡しただけでは
        multiple_unresolvedのままであることを確認する（business_mode_hintは現状inert）。"""
        path = tmp_path / "hint_only.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},
                {"store_code": "AU1K1234567", "intro_total": 5, "voice_callout_total": 0, "business_date": SERIAL_20260626},
            ],
        )
        from src.phase6.csv_candidate_resolver import BusinessMode

        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
                business_mode_hint=BusinessMode.STORE,  # ヒントだけを渡す。resolution_ruleは渡さない
            )
        )
        assert result.csv_match_status == CsvMatchStatus.MULTIPLE_UNRESOLVED
        assert result.resolved_candidate_row is None

    def test_resolution_rule_with_basis_and_id_succeeds(self, tmp_path):
        path = tmp_path / "rule_with_basis.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},
                {"store_code": "AU1K1234567", "intro_total": 5, "voice_callout_total": 0, "business_date": SERIAL_20260626},
            ],
        )

        def pick_first(candidates):
            return candidates[0]

        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
                resolution_rule=pick_first,
                resolution_rule_basis="テスト用: 先頭行採用ルール(仮)",
                resolution_rule_id="test.pick_first_v1",
            )
        )
        assert result.csv_match_status == CsvMatchStatus.RESOLVED_BY_RULE
        assert result.resolved_candidate_row.intro_total == 3
        assert result.csv_review_required is False
        assert "test.pick_first_v1" in result.resolution_basis
        assert "テスト用" in result.resolution_basis

    def test_resolution_rule_returning_row_outside_candidates_raises(self, tmp_path):
        """resolution_ruleがexact_matches以外の行(候補外)を返した場合は
        InvalidResolutionRuleErrorとし、暗黙的に受理しない。"""
        path = tmp_path / "rule_outside.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},
                {"store_code": "AU1K1234567", "intro_total": 5, "voice_callout_total": 0, "business_date": SERIAL_20260626},
            ],
        )
        from src.phase6.csv_candidate_resolver import CsvCandidateRow

        foreign_row = CsvCandidateRow(
            source_file="other.xlsx",
            sheet_name="CSV",
            row_number=999,
            data_row_index=997,
            store_code="AU1K9999999",
            business_date="2026-06-26",
            business_mode="unknown",
            intro_total=1,
            voice_callout_total=1,
        )

        def return_foreign_row(candidates):
            return foreign_row  # exact_matchesに含まれない行を返す

        with pytest.raises(InvalidResolutionRuleError):
            resolve_csv_candidates(
                CsvResolverInput(
                    source_file=str(path),
                    sheet_name="CSV",
                    selected_business_date="2026-06-26",
                    store_code="AU1K1234567",
                    store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
                    resolution_rule=return_foreign_row,
                    resolution_rule_basis="テスト用: 不正なルール",
                    resolution_rule_id="test.invalid_rule",
                )
            )

    def test_resolution_rule_returning_none_falls_back_to_multiple_unresolved(self, tmp_path):
        """ルールが解決を断念(None)した場合、先頭行等を暗黙採用せずmultiple_unresolvedにする。"""
        path = tmp_path / "rule_declines.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},
                {"store_code": "AU1K1234567", "intro_total": 5, "voice_callout_total": 0, "business_date": SERIAL_20260626},
            ],
        )

        def decline(candidates):
            return None

        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
                resolution_rule=decline,
                resolution_rule_basis="テスト用: 常に断念するルール",
                resolution_rule_id="test.always_decline",
            )
        )
        assert result.csv_match_status == CsvMatchStatus.MULTIPLE_UNRESOLVED
        assert result.resolved_candidate_row is None

    def test_p23_style_multiple_candidates_without_any_rule_stays_unresolved(self, tmp_path):
        """先方確認済みルールが無い現状の運用を模した確認: resolution_ruleを渡さなければ
        P23のような複数候補ケースは常にmultiple_unresolvedのままになる。"""
        path = tmp_path / "no_rule_available.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1KW740165", "intro_total": 6, "voice_callout_total": 0, "business_date": SERIAL_20260627},
                {"store_code": "AU1KW740165", "intro_total": 5, "voice_callout_total": 0, "business_date": SERIAL_20260627},
            ],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-27",
                store_code="AU1KW740165",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
                # resolution_ruleを渡さない = 現状の実運用そのもの
            )
        )
        assert result.csv_match_status == CsvMatchStatus.MULTIPLE_UNRESOLVED
        assert result.resolved_candidate_row is None


class TestSerialization:
    """CsvResolutionResult.to_dict() が json.dumps() 可能であることを確認する
    （レビュー指摘4点目）。Enum・ネストしたdataclass・None・空リストの扱いを検証する。"""

    def test_unique_match_result_is_json_serializable(self, tmp_path):
        path = tmp_path / "serialize_unique.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        d = result.to_dict()
        serialized = json.dumps(d, ensure_ascii=False)  # 例外を送出しないこと
        reloaded = json.loads(serialized)

        assert reloaded["csv_match_status"] == "unique_match"  # Enumが文字列になっている
        assert isinstance(reloaded["resolved_candidate_row"], dict)  # CsvCandidateRowが辞書になっている
        assert reloaded["resolved_candidate_row"]["store_code"] == "AU1K1234567"
        assert reloaded["resolved_candidate_row"]["intro_total"] == 3
        assert reloaded["resolved_candidate_row"]["business_mode"] == "unknown"  # ネストしたEnumも文字列化
        assert reloaded["near_match_candidates"] == []
        assert reloaded["csv_review_reasons"] == []
        assert reloaded["csv_review_required"] is False

    def test_multiple_unresolved_result_is_json_serializable(self, tmp_path):
        path = tmp_path / "serialize_multi.xlsx"
        _write_workbook(
            path,
            [
                {"store_code": "AU1K1234567", "intro_total": 3, "voice_callout_total": 1, "business_date": SERIAL_20260626},
                {"store_code": "AU1K1234567", "intro_total": 5, "voice_callout_total": 0, "business_date": SERIAL_20260626},
            ],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        d = result.to_dict()
        serialized = json.dumps(d, ensure_ascii=False)
        reloaded = json.loads(serialized)

        assert reloaded["csv_match_status"] == "multiple_unresolved"
        assert reloaded["resolved_candidate_row"] is None  # Noneがnullとして保持される
        assert isinstance(reloaded["csv_candidate_rows"], list)
        assert len(reloaded["csv_candidate_rows"]) == 2
        assert all(isinstance(r, dict) for r in reloaded["csv_candidate_rows"])

    def test_not_found_with_near_match_result_is_json_serializable(self, tmp_path):
        path = tmp_path / "serialize_near.xlsx"
        _write_workbook(
            path,
            [{"store_code": "AU1K1234568", "intro_total": 1, "voice_callout_total": 0, "business_date": SERIAL_20260626}],
        )
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(path),
                sheet_name="CSV",
                selected_business_date="2026-06-26",
                store_code="AU1K1234567",
                store_code_resolution_source=StoreCodeResolutionSource.DIRECT_FORM_READ,
            )
        )
        d = result.to_dict()
        serialized = json.dumps(d, ensure_ascii=False)  # near_match_candidatesが辞書配列になること
        reloaded = json.loads(serialized)

        assert reloaded["csv_match_status"] == "not_found"
        assert reloaded["resolved_candidate_row"] is None
        assert isinstance(reloaded["near_match_candidates"], list)
        assert len(reloaded["near_match_candidates"]) == 1
        assert isinstance(reloaded["near_match_candidates"][0], dict)
        assert reloaded["near_match_candidates"][0]["candidate_store_code"] == "AU1K1234568"

    def test_reference_match_unverified_result_is_json_serializable(self):
        result = resolve_csv_candidates(
            CsvResolverInput(
                source_file=str(FILE_0625),
                sheet_name="CSV",
                selected_business_date="2026-06-25",
                store_code="AU1KW740082",
                store_code_resolution_source=StoreCodeResolutionSource.UNVERIFIED_REFERENCE,
            )
        )
        serialized = json.dumps(result.to_dict(), ensure_ascii=False)
        reloaded = json.loads(serialized)
        assert reloaded["csv_match_status"] == "reference_match_unverified"
        assert reloaded["resolved_candidate_row"] is None
        assert reloaded["resolution_basis"] == "ai_store_name_plus_unverified_reference_master"
