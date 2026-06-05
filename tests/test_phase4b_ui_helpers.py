"""
Phase 4b: UI Helper関数テストスイート

目的：
- Helper関数がPhase 1-4a の結果を正しくフォーマットするか検証
- ページサマリーテーブル、複数候補、フィールド比較をテスト
- ダウンロード用CSV生成をテスト
"""

import pytest
import pandas as pd
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from helpers.result_display import (
    format_page_summary_table,
    format_candidate_scores_table,
    format_field_comparison_table,
    generate_download_csv,
)


class TestFormatPageSummaryTable:
    """ページサマリーテーブルのテスト"""

    def test_format_empty_results(self):
        """空リストの場合"""
        result = format_page_summary_table([])
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_format_single_result_match(self):
        """単一結果（match）のフォーマット"""
        results = [
            {
                'page_no': 1,
                'pdf_date': '2026/05/17',
                'pdf_store_name': '小倉',
                'store_code': 'AU1K0024112',
                'status': 'match',
                'match_status': 'candidate_found',
                'csv_candidate_count': 1,
                'field_comparison_summary': {
                    'compared_fields': 12,
                    'matched_fields': 12,
                    'mismatched_fields': 0,
                },
                'review_reasons': [],
            }
        ]

        df = format_page_summary_table(results)

        assert len(df) == 1
        assert df.iloc[0]['Page'] == 1
        assert df.iloc[0]['Status'] == 'match'
        assert df.iloc[0]['Match Rate'] == '100.0%'
        assert df.iloc[0]['Issues'] == 'OK'

    def test_format_single_result_mismatch(self):
        """単一結果（mismatch）のフォーマット"""
        results = [
            {
                'page_no': 2,
                'pdf_date': '2026/05/17',
                'pdf_store_name': '梅田',
                'store_code': 'AU1K0024113',
                'status': 'mismatch',
                'match_status': 'candidate_found',
                'csv_candidate_count': 1,
                'field_comparison_summary': {
                    'compared_fields': 12,
                    'matched_fields': 10,
                    'mismatched_fields': 2,
                },
                'review_reasons': ['2 mismatched fields'],
            }
        ]

        df = format_page_summary_table(results)

        assert len(df) == 1
        assert df.iloc[0]['Status'] == 'mismatch'
        assert df.iloc[0]['Match Rate'] == '83.3%'
        assert '2 mismatch' in df.iloc[0]['Issues']

    def test_format_multiple_candidates(self):
        """複数候補の場合"""
        results = [
            {
                'page_no': 3,
                'pdf_date': '2026/05/17',
                'pdf_store_name': '京都',
                'store_code': 'AU1K0024114',
                'status': 'review',
                'match_status': 'multiple_csv_candidates',
                'csv_candidate_count': 2,
                'field_comparison_summary': {
                    'compared_fields': 12,
                    'matched_fields': 10,
                    'mismatched_fields': 2,
                },
                'candidate_scores': [
                    {
                        'score_rank': 1,
                        'score': 285,
                        'recommendation': 'best_match',
                        'confidence': 'high',
                    }
                ],
                'review_reasons': ['Multiple CSV candidates (2 rows)'],
            }
        ]

        df = format_page_summary_table(results)

        assert len(df) == 1
        assert df.iloc[0]['Status'] == 'review'
        assert df.iloc[0]['Candidates'] == 2
        assert df.iloc[0]['Recommendation'] == 'best_match'
        assert df.iloc[0]['Confidence'] == 'high'

    def test_format_no_comparable_fields(self):
        """比較対象がない場合"""
        results = [
            {
                'page_no': 4,
                'pdf_date': '2026/05/17',
                'pdf_store_name': '大阪',
                'store_code': None,
                'status': 'review',
                'match_status': 'no_csv_candidate',
                'csv_candidate_count': 0,
                'field_comparison_summary': {
                    'compared_fields': 0,
                    'matched_fields': 0,
                    'mismatched_fields': 0,
                },
                'review_reasons': ['No CSV candidates found'],
            }
        ]

        df = format_page_summary_table(results)

        assert len(df) == 1
        assert df.iloc[0]['Status'] == 'review'
        assert df.iloc[0]['Match Rate'] == '0.0%'


class TestFormatCandidateScoresTable:
    """複数候補テーブルのテスト"""

    def test_format_empty_candidates(self):
        """空候補リスト"""
        result = format_candidate_scores_table([])
        assert result is None

    def test_format_none_candidates(self):
        """None の場合"""
        result = format_candidate_scores_table(None)
        assert result is None

    def test_format_single_candidate(self):
        """単一候補"""
        candidates = [
            {
                'score_rank': 1,
                'candidate_index': 0,
                'score': 285.0,
                'match_rate': 0.833,
                'confidence': 'high',
                'matched_fields': 10,
                'mismatched_fields': 2,
                'skipped_fields': 171,
                'recommendation': 'best_match',
            }
        ]

        df = format_candidate_scores_table(candidates)

        assert df is not None
        assert len(df) == 1
        assert df.iloc[0]['Rank'] == 1
        assert df.iloc[0]['Score'] == '285.0'
        assert df.iloc[0]['Match Rate'] == '83.3%'
        assert df.iloc[0]['Confidence'] == 'high'

    def test_format_multiple_candidates(self):
        """複数候補"""
        candidates = [
            {
                'score_rank': 1,
                'candidate_index': 0,
                'score': 285.0,
                'match_rate': 0.833,
                'confidence': 'high',
                'matched_fields': 10,
                'mismatched_fields': 2,
                'skipped_fields': 171,
                'recommendation': 'best_match',
            },
            {
                'score_rank': 2,
                'candidate_index': 1,
                'score': 135.0,
                'match_rate': 0.667,
                'confidence': 'medium',
                'matched_fields': 8,
                'mismatched_fields': 4,
                'skipped_fields': 171,
                'recommendation': 'ambiguous',
            },
        ]

        df = format_candidate_scores_table(candidates)

        assert df is not None
        assert len(df) == 2
        assert df.iloc[0]['Rank'] == 1
        assert df.iloc[1]['Rank'] == 2
        assert df.iloc[0]['Score'] == '285.0'
        assert df.iloc[1]['Score'] == '135.0'


class TestFormatFieldComparisonTable:
    """フィールド比較テーブルのテスト"""

    def test_format_empty_comparisons(self):
        """空比較リスト"""
        result = format_field_comparison_table([])
        assert result is None

    def test_format_none_comparisons(self):
        """None の場合"""
        result = format_field_comparison_table(None)
        assert result is None

    def test_format_match_field(self):
        """一致フィールド"""
        comparisons = [
            {
                'fax_item_name': 'AU案件新規紹介数',
                'csv_column_code': 'AU',
                'csv_column_name': 'au案件新規紹介数',
                'pdf_value': 5,
                'csv_value': 5,
                'comparison_status': 'match',
                'reason': '',
            }
        ]

        df = format_field_comparison_table(comparisons)

        assert df is not None
        assert len(df) == 1
        assert '✅ match' in df.iloc[0]['Status']
        assert df.iloc[0]['PDF Value'] == '5'
        assert df.iloc[0]['CSV Value'] == '5'

    def test_format_mismatch_field(self):
        """不一致フィールド"""
        comparisons = [
            {
                'fax_item_name': 'DL案件既存紹介数',
                'csv_column_code': 'DL',
                'csv_column_name': 'dl案件既存紹介数',
                'pdf_value': 3,
                'csv_value': 4,
                'comparison_status': 'mismatch',
                'reason': 'PDF=3, CSV=4',
            }
        ]

        df = format_field_comparison_table(comparisons)

        assert df is not None
        assert len(df) == 1
        assert '❌ mismatch' in df.iloc[0]['Status']
        assert df.iloc[0]['PDF Value'] == '3'
        assert df.iloc[0]['CSV Value'] == '4'

    def test_format_skipped_pdf_null(self):
        """PDF値がnull（スキップ）"""
        comparisons = [
            {
                'fax_item_name': 'HJ既存対応',
                'csv_column_code': 'HJ',
                'csv_column_name': 'hj既存対応',
                'pdf_value': None,
                'csv_value': 10,
                'comparison_status': 'skipped_pdf_null',
                'reason': 'PDF value is null',
            }
        ]

        df = format_field_comparison_table(comparisons)

        assert df is not None
        assert len(df) == 1
        assert 'skipped' in df.iloc[0]['Status'].lower()
        assert df.iloc[0]['PDF Value'] == '-'
        assert df.iloc[0]['CSV Value'] == '10'

    def test_format_skipped_pdf_uncertain(self):
        """PDF値が不確定（途中形）"""
        comparisons = [
            {
                'fax_item_name': 'IG既存対応',
                'csv_column_code': 'IG',
                'csv_column_name': 'ig既存対応',
                'pdf_value': 'uncertain',
                'csv_value': 10,
                'comparison_status': 'skipped_pdf_uncertain',
                'reason': 'PDF value is uncertain (tally mark途中形)',
            }
        ]

        df = format_field_comparison_table(comparisons)

        assert df is not None
        assert len(df) == 1
        assert 'uncertain' in df.iloc[0]['Status'].lower()
        assert df.iloc[0]['PDF Value'] == '(要確認)'

    def test_format_mixed_comparisons(self):
        """複合フィールド"""
        comparisons = [
            {
                'fax_item_name': 'AU案件新規紹介数',
                'csv_column_code': 'AU',
                'csv_column_name': 'au案件新規紹介数',
                'pdf_value': 5,
                'csv_value': 5,
                'comparison_status': 'match',
                'reason': '',
            },
            {
                'fax_item_name': 'DL案件既存紹介数',
                'csv_column_code': 'DL',
                'csv_column_name': 'dl案件既存紹介数',
                'pdf_value': 3,
                'csv_value': 4,
                'comparison_status': 'mismatch',
                'reason': 'Values differ',
            },
            {
                'fax_item_name': 'HJ既存対応',
                'csv_column_code': 'HJ',
                'csv_column_name': 'hj既存対応',
                'pdf_value': None,
                'csv_value': 10,
                'comparison_status': 'skipped_pdf_null',
                'reason': 'PDF value is null',
            },
        ]

        df = format_field_comparison_table(comparisons)

        assert df is not None
        assert len(df) == 3
        assert '✅ match' in df.iloc[0]['Status']
        assert '❌ mismatch' in df.iloc[1]['Status']
        assert 'skipped' in df.iloc[2]['Status'].lower()


class TestGenerateDownloadCsv:
    """ダウンロード用CSV生成のテスト"""

    def test_generate_empty_results(self):
        """空リストの場合"""
        csv_bytes, filename = generate_download_csv([])

        assert csv_bytes == b''
        assert 'reconciliation_result_' in filename
        assert filename.endswith('.csv')

    def test_generate_single_result(self):
        """単一結果でのCSV生成"""
        results = [
            {
                'page_no': 1,
                'pdf_date': '2026/05/17',
                'pdf_store_name': '小倉',
                'store_code': 'AU1K0024112',
                'status': 'match',
                'match_status': 'candidate_found',
                'csv_candidate_count': 1,
                'field_comparison_summary': {
                    'compared_fields': 12,
                    'matched_fields': 12,
                    'mismatched_fields': 0,
                },
                'review_reasons': [],
            }
        ]

        csv_bytes, filename = generate_download_csv(results)

        assert csv_bytes != b''
        assert 'reconciliation_result_' in filename
        assert filename.endswith('.csv')

        # CSV内容を確認
        csv_content = csv_bytes.decode('utf-8-sig')
        assert 'page_number' in csv_content
        assert 'pdf_date' in csv_content
        assert 'match_status' in csv_content
        assert '2026/05/17' in csv_content
        assert '小倉' in csv_content

    def test_generate_multiple_results(self):
        """複数結果でのCSV生成"""
        results = [
            {
                'page_no': 1,
                'pdf_date': '2026/05/17',
                'pdf_store_name': '小倉',
                'store_code': 'AU1K0024112',
                'status': 'match',
                'match_status': 'candidate_found',
                'csv_candidate_count': 1,
                'field_comparison_summary': {
                    'compared_fields': 12,
                    'matched_fields': 12,
                    'mismatched_fields': 0,
                },
                'review_reasons': [],
            },
            {
                'page_no': 2,
                'pdf_date': '2026/05/17',
                'pdf_store_name': '梅田',
                'store_code': 'AU1K0024113',
                'status': 'mismatch',
                'match_status': 'candidate_found',
                'csv_candidate_count': 1,
                'field_comparison_summary': {
                    'compared_fields': 12,
                    'matched_fields': 10,
                    'mismatched_fields': 2,
                },
                'review_reasons': ['2 mismatched fields'],
            },
        ]

        csv_bytes, filename = generate_download_csv(results)

        assert csv_bytes != b''
        csv_content = csv_bytes.decode('utf-8-sig')

        # 両方のレコードが含まれていることを確認
        lines = csv_content.strip().split('\n')
        assert len(lines) == 3  # ヘッダー + 2行

    def test_generate_csv_with_review_reasons(self):
        """Review reasonsが含まれている場合"""
        results = [
            {
                'page_no': 3,
                'pdf_date': '2026/05/17',
                'pdf_store_name': '京都',
                'store_code': None,
                'status': 'review',
                'match_status': 'multiple_csv_candidates',
                'csv_candidate_count': 2,
                'field_comparison_summary': {
                    'compared_fields': 0,
                    'matched_fields': 0,
                    'mismatched_fields': 0,
                },
                'review_reasons': [
                    'Multiple CSV candidates (2 rows)',
                    'Field comparison pending',
                ],
            }
        ]

        csv_bytes, filename = generate_download_csv(results)

        assert csv_bytes != b''
        csv_content = csv_bytes.decode('utf-8-sig')
        assert 'Multiple CSV candidates' in csv_content


class TestIntegration:
    """統合テスト"""

    def test_format_all_tables_together(self):
        """全ヘルパー関数を組み合わせて使用"""
        results = [
            {
                'page_no': 1,
                'pdf_date': '2026/05/17',
                'pdf_store_name': '小倉',
                'store_code': 'AU1K0024112',
                'status': 'review',
                'match_status': 'multiple_csv_candidates',
                'csv_candidate_count': 2,
                'field_comparison_summary': {
                    'compared_fields': 12,
                    'matched_fields': 10,
                    'mismatched_fields': 2,
                },
                'candidate_scores': [
                    {
                        'score_rank': 1,
                        'candidate_index': 0,
                        'score': 285.0,
                        'match_rate': 0.833,
                        'confidence': 'high',
                        'matched_fields': 10,
                        'mismatched_fields': 2,
                        'skipped_fields': 171,
                        'recommendation': 'best_match',
                    },
                    {
                        'score_rank': 2,
                        'candidate_index': 1,
                        'score': 135.0,
                        'match_rate': 0.667,
                        'confidence': 'medium',
                        'matched_fields': 8,
                        'mismatched_fields': 4,
                        'skipped_fields': 171,
                        'recommendation': 'ambiguous',
                    },
                ],
                'field_comparisons': [
                    {
                        'fax_item_name': 'AU案件新規紹介数',
                        'csv_column_code': 'AU',
                        'csv_column_name': 'au案件新規紹介数',
                        'pdf_value': 5,
                        'csv_value': 5,
                        'comparison_status': 'match',
                        'reason': '',
                    },
                ],
                'review_reasons': ['Multiple CSV candidates (2 rows)'],
            }
        ]

        # 全ヘルパー関数を実行
        summary_df = format_page_summary_table(results)
        candidate_df = format_candidate_scores_table(results[0]['candidate_scores'])
        field_df = format_field_comparison_table(results[0]['field_comparisons'])
        csv_bytes, filename = generate_download_csv(results)

        # すべてが正常に生成されたことを確認
        assert len(summary_df) == 1
        assert len(candidate_df) == 2
        assert len(field_df) == 1
        assert csv_bytes != b''


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
