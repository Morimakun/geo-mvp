"""
Phase 2 CSV Candidate Matching Tests

テスト対象：
- 日付 + 店舗コード による CSV 候補マッチング
- 日付正規化（複数形式対応）
- 候補数ごとの分類（1件/0件/複数件）
"""

import unittest
import pandas as pd
from pathlib import Path
import sys
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from reconciliation_phase1 import Phase1ReconciliationEngine


class TestPhase2CSVCandidateMatching(unittest.TestCase):
    """Phase 2 CSV 候補マッチングのテストケース"""

    @classmethod
    def setUpClass(cls):
        """テストクラス初期化"""
        # マスタデータ読み込み
        cls.store_code_mapping = pd.read_csv(
            Path(__file__).parent.parent / "data" / "master" / "store_code_mapping.csv"
        )

        # PDF×CSV フィールドマッピング読み込み
        cls.pdf_csv_mapping = pd.read_csv(
            Path(__file__).parent.parent / "data" / "master" / "pdf_csv_field_mapping.csv"
        )

        # スタッフマスタ読み込み
        cls.staff_master = pd.DataFrame({
            'staff_name': ['田中', '佐藤'],
            'staff_no': [1001, 1002]
        })

        # エンジン初期化
        cls.engine = Phase1ReconciliationEngine(
            mapping_table=cls.pdf_csv_mapping,
            store_master=cls.store_code_mapping,
            staff_master=cls.staff_master
        )

    def _create_test_csv_dataframe(self, store_code: str, date_str: str, row_count: int = 1) -> pd.DataFrame:
        """テスト用 CSV DataFrame を作成"""
        # CSV 列 281（0-indexed: 280）に店舗コードを配置
        # CSV 列 A（0-indexed: 0）に日付を配置
        data = {
            'A': [date_str] * row_count,  # 日付列
        }

        # 列 280（0-indexed）に店舗コード列を配置
        for i in range(281):
            if i == 0:
                # 既に 'A' で埋めている
                continue
            elif i == 280:
                # 店舗コード列
                data[f'col_{i}'] = [store_code] * row_count
            else:
                # その他の列
                data[f'col_{i}'] = [None] * row_count

        df = pd.DataFrame(data)
        return df

    def test_single_candidate_match(self):
        """テスト1: 日付 + store_code で 1 件ヒット"""
        # Arrange
        target_store_code = self.store_code_mapping.iloc[0]['store_code']
        target_date = '2026/06/05'

        csv_data = self._create_test_csv_dataframe(target_store_code, target_date, row_count=1)

        # Act
        review_reasons = []
        result = self.engine._find_csv_candidates(
            store_code=target_store_code,
            csv_target=csv_data,
            target_date=target_date,
            review_reasons=review_reasons
        )

        # Assert
        self.assertEqual(result['match_status'], 'candidate_found',
                        f"Expected 'candidate_found', got '{result['match_status']}'")
        self.assertEqual(result['csv_candidate_count'], 1,
                        f"Expected 1 candidate, got {result['csv_candidate_count']}")
        self.assertIsNotNone(result['best_match'],
                            "best_match should not be None for single candidate")
        self.assertFalse(result['candidates_df'].empty,
                        "candidates_df should not be empty")

        print(f"[OK] Single candidate match: store_code={target_store_code}, date={target_date}")

    def test_no_candidate_wrong_store_code(self):
        """テスト2: 店舗コード不一致で 0 件ヒット"""
        # Arrange
        target_store_code_pdf = self.store_code_mapping.iloc[0]['store_code']
        wrong_store_code_csv = "AU1KWXXX9999"  # 存在しないコード
        target_date = '2026/06/05'

        csv_data = self._create_test_csv_dataframe(wrong_store_code_csv, target_date, row_count=1)

        # Act
        review_reasons = []
        result = self.engine._find_csv_candidates(
            store_code=target_store_code_pdf,
            csv_target=csv_data,
            target_date=target_date,
            review_reasons=review_reasons
        )

        # Assert
        self.assertEqual(result['match_status'], 'no_csv_candidate',
                        "Expected 'no_csv_candidate' for wrong store code")
        self.assertEqual(result['csv_candidate_count'], 0)
        self.assertTrue(result['candidates_df'].empty)
        self.assertTrue(any('candidate' in r.lower() for r in review_reasons),
                       "review_reasons should mention no candidates found")

        print(f"[OK] No candidate (wrong store code): {target_store_code_pdf}")

    def test_no_candidate_date_mismatch(self):
        """テスト3: 日付不一致で 0 件ヒット"""
        # Arrange
        target_store_code = self.store_code_mapping.iloc[0]['store_code']
        pdf_date = '2026/06/05'
        csv_date = '2026/06/04'  # 異なる日付

        csv_data = self._create_test_csv_dataframe(target_store_code, csv_date, row_count=1)

        # Act
        review_reasons = []
        result = self.engine._find_csv_candidates(
            store_code=target_store_code,
            csv_target=csv_data,
            target_date=pdf_date,
            review_reasons=review_reasons
        )

        # Assert
        self.assertEqual(result['match_status'], 'no_csv_candidate',
                        "Expected 'no_csv_candidate' for date mismatch")
        self.assertEqual(result['csv_candidate_count'], 0)
        self.assertTrue(any('date' in r.lower() for r in review_reasons),
                       "review_reasons should mention date-related issue")

        print(f"[OK] No candidate (date mismatch): PDF={pdf_date}, CSV={csv_date}")

    def test_multiple_candidates(self):
        """テスト4: 同日付・同店舗で複数行ヒット"""
        # Arrange
        target_store_code = self.store_code_mapping.iloc[0]['store_code']
        target_date = '2026/06/05'

        # 同日付・同店舗で 2 行
        csv_data = self._create_test_csv_dataframe(target_store_code, target_date, row_count=2)

        # Act
        review_reasons = []
        result = self.engine._find_csv_candidates(
            store_code=target_store_code,
            csv_target=csv_data,
            target_date=target_date,
            review_reasons=review_reasons
        )

        # Assert
        self.assertEqual(result['match_status'], 'multiple_csv_candidates',
                        "Expected 'multiple_csv_candidates'")
        self.assertEqual(result['csv_candidate_count'], 2,
                        f"Expected 2 candidates, got {result['csv_candidate_count']}")
        self.assertFalse(result['candidates_df'].empty)
        self.assertTrue(any('multiple' in r.lower() for r in review_reasons),
                       "review_reasons should mention multiple candidates")

        print(f"[OK] Multiple candidates: 2 rows for store_code={target_store_code}")

    def test_store_code_none(self):
        """テスト5: store_code が None（Phase 1 で変換失敗）"""
        # Arrange
        target_date = '2026/06/05'
        csv_data = self._create_test_csv_dataframe("AU1KW740165", target_date, row_count=1)

        # Act
        review_reasons = []
        result = self.engine._find_csv_candidates(
            store_code=None,  # 不明
            csv_target=csv_data,
            target_date=target_date,
            review_reasons=review_reasons
        )

        # Assert
        self.assertEqual(result['match_status'], 'no_csv_candidate')
        self.assertTrue(any('store code' in r.lower() for r in review_reasons),
                       "review_reasons should mention store code issue")

        print(f"[OK] store_code=None handled correctly")

    def test_date_format_variation_slash(self):
        """テスト6a: 日付形式 YYYY/MM/DD"""
        # Arrange
        target_store_code = self.store_code_mapping.iloc[0]['store_code']
        pdf_date = '2026/06/05'
        csv_date = '2026/06/05'

        csv_data = self._create_test_csv_dataframe(target_store_code, csv_date, row_count=1)

        # Act
        review_reasons = []
        result = self.engine._find_csv_candidates(
            store_code=target_store_code,
            csv_target=csv_data,
            target_date=pdf_date,
            review_reasons=review_reasons
        )

        # Assert
        self.assertEqual(result['match_status'], 'candidate_found',
                        f"Expected 'candidate_found' for YYYY/MM/DD format")
        self.assertEqual(result['csv_candidate_count'], 1)

        print(f"[OK] Date format YYYY/MM/DD: {pdf_date}")

    def test_date_format_variation_dash(self):
        """テスト6b: 日付形式 YYYY-MM-DD"""
        # Arrange
        target_store_code = self.store_code_mapping.iloc[0]['store_code']
        pdf_date = '2026-06-05'  # ダッシュ
        csv_date = '2026/06/05'  # スラッシュ

        csv_data = self._create_test_csv_dataframe(target_store_code, csv_date, row_count=1)

        # Act
        review_reasons = []
        result = self.engine._find_csv_candidates(
            store_code=target_store_code,
            csv_target=csv_data,
            target_date=pdf_date,
            review_reasons=review_reasons
        )

        # Assert
        self.assertEqual(result['match_status'], 'candidate_found',
                        f"Expected 'candidate_found' for YYYY-MM-DD format")
        self.assertEqual(result['csv_candidate_count'], 1)

        print(f"[OK] Date format YYYY-MM-DD: {pdf_date}")

    def test_date_format_variation_japanese(self):
        """テスト6c: 日付形式 YYYY年MM月DD日"""
        # Arrange
        target_store_code = self.store_code_mapping.iloc[0]['store_code']
        pdf_date = '2026年6月5日'  # 日本語形式
        csv_date = '2026/06/05'

        csv_data = self._create_test_csv_dataframe(target_store_code, csv_date, row_count=1)

        # Act
        review_reasons = []
        result = self.engine._find_csv_candidates(
            store_code=target_store_code,
            csv_target=csv_data,
            target_date=pdf_date,
            review_reasons=review_reasons
        )

        # Assert
        self.assertEqual(result['match_status'], 'candidate_found',
                        f"Expected 'candidate_found' for Japanese date format")
        self.assertEqual(result['csv_candidate_count'], 1)

        print(f"[OK] Date format YYYY年MM月DD日: {pdf_date}")

    def test_date_format_variation_yyyymmdd(self):
        """テスト6d: 日付形式 YYYYMMDD（区切りなし）"""
        # Arrange
        target_store_code = self.store_code_mapping.iloc[0]['store_code']
        pdf_date = '20260605'  # 区切りなし
        csv_date = '2026/06/05'

        csv_data = self._create_test_csv_dataframe(target_store_code, csv_date, row_count=1)

        # Act
        review_reasons = []
        result = self.engine._find_csv_candidates(
            store_code=target_store_code,
            csv_target=csv_data,
            target_date=pdf_date,
            review_reasons=review_reasons
        )

        # Assert
        self.assertEqual(result['match_status'], 'candidate_found',
                        f"Expected 'candidate_found' for YYYYMMDD format")
        self.assertEqual(result['csv_candidate_count'], 1)

        print(f"[OK] Date format YYYYMMDD: {pdf_date}")

    def test_date_format_variation_datetime(self):
        """テスト6e: pandas Timestamp"""
        # Arrange
        target_store_code = self.store_code_mapping.iloc[0]['store_code']
        pdf_date = pd.Timestamp('2026-06-05')  # pandas Timestamp
        csv_date = '2026/06/05'

        csv_data = self._create_test_csv_dataframe(target_store_code, csv_date, row_count=1)

        # Act
        review_reasons = []
        result = self.engine._find_csv_candidates(
            store_code=target_store_code,
            csv_target=csv_data,
            target_date=pdf_date,
            review_reasons=review_reasons
        )

        # Assert
        self.assertEqual(result['match_status'], 'candidate_found',
                        f"Expected 'candidate_found' for pandas Timestamp")
        self.assertEqual(result['csv_candidate_count'], 1)

        print(f"[OK] Date format pandas.Timestamp: {pdf_date}")


class TestDateNormalization(unittest.TestCase):
    """日付正規化ロジックのテスト"""

    @classmethod
    def setUpClass(cls):
        """初期化"""
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

        cls.engine = Phase1ReconciliationEngine(
            mapping_table=cls.pdf_csv_mapping,
            store_master=cls.store_code_mapping,
            staff_master=cls.staff_master
        )

    def test_normalize_date_yyyy_slash_mm_dd(self):
        """YYYY/MM/DD を正規化"""
        normalized, status = self.engine._normalize_date('2026/06/05')
        self.assertEqual(normalized, '2026/06/05')
        self.assertEqual(status, 'success')

    def test_normalize_date_yyyy_dash_mm_dd(self):
        """YYYY-MM-DD を YYYY/MM/DD に"""
        normalized, status = self.engine._normalize_date('2026-06-05')
        self.assertEqual(normalized, '2026/06/05')
        self.assertEqual(status, 'success')

    def test_normalize_date_japanese(self):
        """YYYY年MM月DD日 を YYYY/MM/DD に"""
        normalized, status = self.engine._normalize_date('2026年6月5日')
        self.assertEqual(normalized, '2026/06/05')
        self.assertEqual(status, 'success')

    def test_normalize_date_yyyymmdd(self):
        """YYYYMMDD を YYYY/MM/DD に"""
        normalized, status = self.engine._normalize_date('20260605')
        self.assertEqual(normalized, '2026/06/05')
        self.assertEqual(status, 'success')

    def test_normalize_date_timestamp(self):
        """pandas Timestamp を YYYY/MM/DD に"""
        ts = pd.Timestamp('2026-06-05')
        normalized, status = self.engine._normalize_date(ts)
        self.assertEqual(normalized, '2026/06/05')
        self.assertEqual(status, 'success')

    def test_normalize_date_datetime(self):
        """datetime を YYYY/MM/DD に"""
        dt = datetime(2026, 6, 5)
        normalized, status = self.engine._normalize_date(dt)
        self.assertEqual(normalized, '2026/06/05')
        self.assertEqual(status, 'success')

    def test_normalize_date_none(self):
        """None は失敗を返す"""
        normalized, status = self.engine._normalize_date(None)
        self.assertIsNone(normalized)
        self.assertEqual(status, 'failed')

    def test_normalize_date_invalid(self):
        """不正なフォーマットは失敗を返す"""
        normalized, status = self.engine._normalize_date('invalid-date')
        self.assertIsNone(normalized)
        self.assertEqual(status, 'failed')


class TestPhase2IntegrationWithPhase1(unittest.TestCase):
    """Phase 2 と Phase 1 の統合テスト"""

    @classmethod
    def setUpClass(cls):
        """初期化"""
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

        cls.engine = Phase1ReconciliationEngine(
            mapping_table=cls.pdf_csv_mapping,
            store_master=cls.store_code_mapping,
            staff_master=cls.staff_master
        )

    def test_phase1_phase2_flow_no_candidate(self):
        """Phase 1 → Phase 2 フロー（候補なし）"""
        # ダミー CSV
        csv_data = pd.DataFrame({
            'A': ['2026/06/05'],
            'col_280': ['AU1KWXXX9999'],  # 存在しないコード
        })

        # PDF レコード
        pdf_record = {
            'page_no': 1,
            'store_name': self.store_code_mapping.iloc[0]['store_name'],
            'staff_name': None,
            'tablet_no': None,
            'data_no': None,
            'mapped_values': {}
        }

        # 照合実行
        result = self.engine.reconcile_pdf_with_csv(
            pdf_record,
            csv_data,
            '2026/06/05'
        )

        # 検証
        self.assertEqual(result['status'], 'review',
                        "Status should be 'review' when no CSV candidate is found")
        self.assertIn('match_status', result)
        self.assertEqual(result['match_status'], 'no_csv_candidate')

        print(f"[OK] Phase 1-2 integration (no candidate): status={result['status']}")


if __name__ == '__main__':
    # テスト実行（詳細出力）
    unittest.main(verbosity=2)
