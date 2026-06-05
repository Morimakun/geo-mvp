"""
Phase 3 Field Comparison Tests

テスト対象：
- confirmed項目のPDF値とCSV値の比較
- 数値正規化
- 比較結果の分類（match/mismatch/skipped）
- 最終ステータス判定
"""

import unittest
import pandas as pd
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from reconciliation_phase1 import Phase1ReconciliationEngine


class TestPhase3FieldComparison(unittest.TestCase):
    """Phase 3 フィールド比較のテストケース"""

    @classmethod
    def setUpClass(cls):
        """テストクラス初期化"""
        # マスタデータ読み込み
        cls.store_code_mapping = pd.read_csv(
            Path(__file__).parent.parent / "data" / "master" / "store_code_mapping.csv"
        )

        cls.pdf_csv_mapping = pd.read_csv(
            Path(__file__).parent.parent / "data" / "master" / "pdf_csv_field_mapping.csv"
        )

        cls.staff_master = pd.DataFrame({
            'staff_name': ['田中'],
            'staff_no': [1001]
        })

        # エンジン初期化
        cls.engine = Phase1ReconciliationEngine(
            mapping_table=cls.pdf_csv_mapping,
            store_master=cls.store_code_mapping,
            staff_master=cls.staff_master
        )

    def _create_test_csv_row(self, values_dict: dict) -> pd.Series:
        """テスト用 CSV 行を作成（最大300列）

        Args:
            values_dict: {csv_column_number: value, ...} (1-indexed)
        """
        # 300列のダミー行を作成
        data = {i: None for i in range(300)}

        # 指定された列に値を設定
        for col_num, value in values_dict.items():
            data[col_num - 1] = value  # 1-indexed → 0-indexed

        return pd.Series(data)

    def test_all_items_match(self):
        """テスト1: 全項目が一致"""
        # Arrange
        target_store_code = self.store_code_mapping.iloc[0]['store_code']

        # confirmed_mapping から最初の10項目を取得
        confirmed_items = self.engine.confirmed_mapping.head(10)

        # PDF レコード（確定済み項目のみ）
        pdf_mapped_values = {}
        csv_values_dict = {}

        for idx, row in confirmed_items.iterrows():
            csv_col_num = row.get('csv_column_number')
            csv_col_code = row.get('csv_column_code')

            if pd.notna(csv_col_num) and pd.notna(csv_col_code):
                # PDF側: 5 を設定
                pdf_mapped_values[csv_col_code] = 5
                # CSV側: 5 を設定
                csv_values_dict[int(csv_col_num)] = 5

        pdf_record = {
            'page_no': 1,
            'store_name': self.store_code_mapping.iloc[0]['store_name'],
            'staff_name': None,
            'tablet_no': None,
            'data_no': None,
            'mapped_values': pdf_mapped_values
        }

        csv_row = self._create_test_csv_row(csv_values_dict)

        csv_match_result = {
            'match_status': 'candidate_found',
            'csv_candidate_count': 1,
            'candidates_df': pd.DataFrame(),
            'best_match': csv_row,
            'normalized_date': '2026/06/05',
        }

        # Act
        result = self.engine._compare_fields(pdf_record, csv_row, csv_match_result)

        # Assert
        summary = result['summary']
        self.assertGreater(summary['compared_fields'], 0, "Should have compared fields")
        self.assertEqual(summary['mismatched_fields'], 0, "Should have no mismatches")
        self.assertGreater(summary['matched_fields'], 0, "Should have some matches")

        print(f"[OK] All items match: {summary['matched_fields']}/{summary['compared_fields']}")

    def test_partial_mismatch_single_item(self):
        """テスト2: 1項目のみ不一致"""
        # Arrange
        confirmed_items = self.engine.confirmed_mapping.head(5)

        pdf_mapped_values = {}
        csv_values_dict = {}
        mismatch_count = 0

        for idx, row in confirmed_items.iterrows():
            csv_col_num = row.get('csv_column_number')
            csv_col_code = row.get('csv_column_code')

            if pd.notna(csv_col_num) and pd.notna(csv_col_code):
                if mismatch_count == 0:
                    # 最初の項目のみ不一致
                    pdf_mapped_values[csv_col_code] = 5
                    csv_values_dict[int(csv_col_num)] = 10  # 異なる値
                    mismatch_count += 1
                else:
                    # 他は一致
                    pdf_mapped_values[csv_col_code] = 3
                    csv_values_dict[int(csv_col_num)] = 3

        pdf_record = {
            'page_no': 1,
            'store_name': self.store_code_mapping.iloc[0]['store_name'],
            'staff_name': None,
            'tablet_no': None,
            'data_no': None,
            'mapped_values': pdf_mapped_values
        }

        csv_row = self._create_test_csv_row(csv_values_dict)

        csv_match_result = {
            'match_status': 'candidate_found',
            'csv_candidate_count': 1,
        }

        # Act
        result = self.engine._compare_fields(pdf_record, csv_row, csv_match_result)

        # Assert
        summary = result['summary']
        self.assertEqual(summary['mismatched_fields'], 1, "Should have 1 mismatch")
        self.assertGreater(summary['matched_fields'], 0, "Should have some matches")

        print(f"[OK] Partial mismatch: {summary['mismatched_fields']} mismatch, {summary['matched_fields']} match")

    def test_pdf_value_null(self):
        """テスト3: PDF値が null"""
        # Arrange
        confirmed_items = self.engine.confirmed_mapping.head(3)

        pdf_mapped_values = {}
        csv_values_dict = {}

        for idx, row in confirmed_items.iterrows():
            csv_col_num = row.get('csv_column_number')
            csv_col_code = row.get('csv_column_code')

            if pd.notna(csv_col_num) and pd.notna(csv_col_code):
                # PDF側: 値なし (null)
                pdf_mapped_values[csv_col_code] = None
                # CSV側: 5
                csv_values_dict[int(csv_col_num)] = 5

        pdf_record = {
            'page_no': 1,
            'store_name': self.store_code_mapping.iloc[0]['store_name'],
            'staff_name': None,
            'tablet_no': None,
            'data_no': None,
            'mapped_values': pdf_mapped_values
        }

        csv_row = self._create_test_csv_row(csv_values_dict)

        csv_match_result = {'match_status': 'candidate_found', 'csv_candidate_count': 1}

        # Act
        result = self.engine._compare_fields(pdf_record, csv_row, csv_match_result)

        # Assert
        comparisons = result['field_comparisons']
        skipped = [c for c in comparisons if c['comparison_status'] == 'skipped_pdf_null']
        self.assertGreater(len(skipped), 0, "Should have skipped entries for null PDF")

        print(f"[OK] PDF null: {len(skipped)} items skipped")

    def test_pdf_value_uncertain(self):
        """テスト4: PDF値が uncertain（正の字途中形）"""
        # Arrange
        confirmed_items = self.engine.confirmed_mapping.head(3)

        pdf_mapped_values = {}
        csv_values_dict = {}

        for idx, row in confirmed_items.iterrows():
            csv_col_num = row.get('csv_column_number')
            csv_col_code = row.get('csv_column_code')

            if pd.notna(csv_col_num) and pd.notna(csv_col_code):
                # PDF側: uncertain
                pdf_mapped_values[csv_col_code] = 'uncertain'
                # CSV側: 5
                csv_values_dict[int(csv_col_num)] = 5

        pdf_record = {
            'page_no': 1,
            'store_name': self.store_code_mapping.iloc[0]['store_name'],
            'staff_name': None,
            'tablet_no': None,
            'data_no': None,
            'mapped_values': pdf_mapped_values
        }

        csv_row = self._create_test_csv_row(csv_values_dict)

        csv_match_result = {'match_status': 'candidate_found', 'csv_candidate_count': 1}

        # Act
        result = self.engine._compare_fields(pdf_record, csv_row, csv_match_result)

        # Assert
        comparisons = result['field_comparisons']
        skipped = [c for c in comparisons if c['comparison_status'] == 'skipped_pdf_uncertain']
        self.assertGreater(len(skipped), 0, "Should have skipped entries for uncertain PDF")

        print(f"[OK] PDF uncertain: {len(skipped)} items skipped (tally mark途中形)")

    def test_csv_value_null(self):
        """テスト5: CSV値が null"""
        # Arrange
        confirmed_items = self.engine.confirmed_mapping.head(3)

        pdf_mapped_values = {}
        csv_values_dict = {}

        for idx, row in confirmed_items.iterrows():
            csv_col_num = row.get('csv_column_number')
            csv_col_code = row.get('csv_column_code')

            if pd.notna(csv_col_num) and pd.notna(csv_col_code):
                # PDF側: 5
                pdf_mapped_values[csv_col_code] = 5
                # CSV側: None (null)
                csv_values_dict[int(csv_col_num)] = None

        pdf_record = {
            'page_no': 1,
            'store_name': self.store_code_mapping.iloc[0]['store_name'],
            'staff_name': None,
            'tablet_no': None,
            'data_no': None,
            'mapped_values': pdf_mapped_values
        }

        csv_row = self._create_test_csv_row(csv_values_dict)

        csv_match_result = {'match_status': 'candidate_found', 'csv_candidate_count': 1}

        # Act
        result = self.engine._compare_fields(pdf_record, csv_row, csv_match_result)

        # Assert
        comparisons = result['field_comparisons']
        skipped = [c for c in comparisons if c['comparison_status'] == 'skipped_csv_null']
        self.assertGreater(len(skipped), 0, "Should have skipped entries for null CSV")

        print(f"[OK] CSV null: {len(skipped)} items skipped")

    def test_exclude_mapping_status_uncertain(self):
        """テスト6: mapping_status=uncertain の項目は除外"""
        # Arrange
        # Phase 1 で confirmed_mapping から uncertain は既に除外されているので、
        # ここでは confirmed_mapping に uncertain がないことを確認

        uncertain_count = len(self.engine.mapping_table[
            self.engine.mapping_table['mapping_status'] == 'uncertain'
        ])

        confirmed_count = len(self.engine.confirmed_mapping)
        mapping_total = len(self.engine.mapping_table[self.engine.mapping_table['mapping_status'] == 'confirmed'])

        # Assert
        # confirmed_mapping は confirmed のみで構成される
        self.assertLessEqual(confirmed_count, mapping_total,
                            "confirmed_mapping should only contain confirmed items")

        print(f"[OK] Exclude uncertain: confirmed={confirmed_count}, uncertain(in all)={uncertain_count}")

    def test_exclude_needs_confirmation_true(self):
        """テスト7: needs_confirmation=true の項目は除外"""
        # Phase 1 で needs_confirmation=false のみ選出されているので、
        # confirmed_mapping に needs_confirmation=true がないことを確認

        needs_confirmation_true_count = len(self.engine.confirmed_mapping[
            (self.engine.confirmed_mapping['needs_confirmation'].astype(str).str.lower() == 'true') |
            (self.engine.confirmed_mapping['needs_confirmation'] == True)
        ])

        # Assert
        self.assertEqual(needs_confirmation_true_count, 0,
                        "confirmed_mapping should not contain needs_confirmation=true")

        print(f"[OK] Exclude needs_confirmation=true: {len(self.engine.confirmed_mapping)} items in confirmed_mapping")

    def test_exclude_empty_csv_column_code(self):
        """テスト8: csv_column_code が空欄の項目は除外"""
        # Phase 1 で csv_column_code が empty のものは除外されている

        empty_code_count = len(self.engine.confirmed_mapping[
            self.engine.confirmed_mapping['csv_column_code'].astype(str).str.strip() == ''
        ])

        # Assert
        self.assertEqual(empty_code_count, 0,
                        "confirmed_mapping should not contain empty csv_column_code")

        print(f"[OK] Exclude empty csv_column_code: 0 empty codes in {len(self.engine.confirmed_mapping)} items")


class TestNormalizeNumericValue(unittest.TestCase):
    """数値正規化のテスト"""

    @classmethod
    def setUpClass(cls):
        """初期化"""
        cls.store_code_mapping = pd.read_csv(
            Path(__file__).parent.parent / "data" / "master" / "store_code_mapping.csv"
        )
        cls.pdf_csv_mapping = pd.read_csv(
            Path(__file__).parent.parent / "data" / "master" / "pdf_csv_field_mapping.csv"
        )
        cls.staff_master = pd.DataFrame({'staff_name': ['田中'], 'staff_no': [1001]})

        cls.engine = Phase1ReconciliationEngine(
            mapping_table=cls.pdf_csv_mapping,
            store_master=cls.store_code_mapping,
            staff_master=cls.staff_master
        )

    def test_normalize_int(self):
        """int 値を正規化"""
        result = self.engine._normalize_numeric_value(5)
        self.assertEqual(result, 5)

    def test_normalize_float(self):
        """float 値を正規化"""
        result = self.engine._normalize_numeric_value(5.0)
        self.assertEqual(result, 5)

    def test_normalize_string_numeric(self):
        """文字列数値を正規化"""
        result = self.engine._normalize_numeric_value("5")
        self.assertEqual(result, 5)

    def test_normalize_string_with_comma(self):
        """カンマ付きの文字列を正規化"""
        result = self.engine._normalize_numeric_value("1,234")
        self.assertEqual(result, 1234)

    def test_normalize_none(self):
        """None は None を返す"""
        result = self.engine._normalize_numeric_value(None)
        self.assertIsNone(result)

    def test_normalize_empty_string(self):
        """空文字列は None を返す"""
        result = self.engine._normalize_numeric_value("")
        self.assertIsNone(result)

    def test_normalize_invalid_string(self):
        """不正な文字列は None を返す"""
        result = self.engine._normalize_numeric_value("invalid")
        self.assertIsNone(result)

    def test_normalize_nan(self):
        """pd.NA は None を返す"""
        result = self.engine._normalize_numeric_value(pd.NA)
        self.assertIsNone(result)


class TestPhase3StatusDetermination(unittest.TestCase):
    """Phase 3 ステータス判定のテスト"""

    @classmethod
    def setUpClass(cls):
        """初期化"""
        cls.store_code_mapping = pd.read_csv(
            Path(__file__).parent.parent / "data" / "master" / "store_code_mapping.csv"
        )
        cls.pdf_csv_mapping = pd.read_csv(
            Path(__file__).parent.parent / "data" / "master" / "pdf_csv_field_mapping.csv"
        )
        cls.staff_master = pd.DataFrame({'staff_name': ['田中'], 'staff_no': [1001]})

        cls.engine = Phase1ReconciliationEngine(
            mapping_table=cls.pdf_csv_mapping,
            store_master=cls.store_code_mapping,
            staff_master=cls.staff_master
        )

    def test_match_all_items_aligned(self):
        """全項目が一致する場合→ match"""
        csv_match_result = {'match_status': 'candidate_found', 'csv_candidate_count': 1}
        comparison_result = {
            'summary': {
                'total_fields': 10,
                'compared_fields': 10,
                'matched_fields': 10,
                'mismatched_fields': 0,
                'skipped_fields': 0,
                'match_rate': 1.0,
            }
        }
        review_reasons = []

        result = self.engine._determine_phase3_status(csv_match_result, comparison_result, review_reasons)

        self.assertEqual(result, 'match')
        print(f"[OK] Match status: {result}")

    def test_mismatch_items_differ(self):
        """不一致項目がある場合→ mismatch"""
        csv_match_result = {'match_status': 'candidate_found', 'csv_candidate_count': 1}
        comparison_result = {
            'summary': {
                'total_fields': 10,
                'compared_fields': 10,
                'matched_fields': 8,
                'mismatched_fields': 2,
                'skipped_fields': 0,
                'match_rate': 0.8,
            }
        }
        review_reasons = []

        result = self.engine._determine_phase3_status(csv_match_result, comparison_result, review_reasons)

        self.assertEqual(result, 'mismatch')
        print(f"[OK] Mismatch status: {result}")

    def test_review_no_csv_candidate(self):
        """CSV候補がない場合→ review"""
        csv_match_result = {'match_status': 'no_csv_candidate', 'csv_candidate_count': 0}
        comparison_result = {
            'summary': {
                'total_fields': 10,
                'compared_fields': 0,
                'matched_fields': 0,
                'mismatched_fields': 0,
                'skipped_fields': 10,
                'match_rate': 0.0,
            }
        }
        review_reasons = []

        result = self.engine._determine_phase3_status(csv_match_result, comparison_result, review_reasons)

        self.assertEqual(result, 'review')
        self.assertTrue(any('no csv' in r.lower() for r in review_reasons))
        print(f"[OK] Review status (no CSV): {result}")

    def test_review_multiple_csv_candidates(self):
        """複数CSV候補がある場合→ review"""
        csv_match_result = {'match_status': 'multiple_csv_candidates', 'csv_candidate_count': 3}
        comparison_result = {
            'summary': {
                'total_fields': 10,
                'compared_fields': 10,
                'matched_fields': 10,
                'mismatched_fields': 0,
                'skipped_fields': 0,
                'match_rate': 1.0,
            }
        }
        review_reasons = []

        result = self.engine._determine_phase3_status(csv_match_result, comparison_result, review_reasons)

        self.assertEqual(result, 'review')
        self.assertTrue(any('multiple' in r.lower() for r in review_reasons))
        print(f"[OK] Review status (multiple candidates): {result}")

    def test_multiple_csv_candidates_with_mismatch_should_still_review(self):
        """複数CSV候補がある場合、field_comparisonで不一致があっても review になること"""
        csv_match_result = {
            'match_status': 'multiple_csv_candidates',
            'csv_candidate_count': 2
        }
        comparison_result = {
            'summary': {
                'total_fields': 10,
                'compared_fields': 10,
                'matched_fields': 8,
                'mismatched_fields': 2,  # 不一致あり
                'skipped_fields': 0,
                'match_rate': 0.8,
            }
        }
        review_reasons = []

        result = self.engine._determine_phase3_status(csv_match_result, comparison_result, review_reasons)

        # 重要: 複数候補がある場合は、不一致があっても mismatch ではなく review になるべき
        self.assertEqual(result, 'review',
                        "Multiple CSV candidates should stay in review status, not mismatch")
        self.assertTrue(any('multiple' in r.lower() for r in review_reasons),
                       "review_reasons should mention multiple candidates")

        print(f"[OK] Multiple CSV candidates with mismatch correctly returns review: {result}")


if __name__ == '__main__':
    # テスト実行（詳細出力）
    unittest.main(verbosity=2)
