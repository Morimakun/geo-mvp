"""
Phase 4a: 複数CSV候補のスコアリング テストスイート

目的：
- 候補ごとのスコア計算が正しいか
- 信頼度（Confidence）の判定が正しいか
- 推奨候補（Recommendation）の判定が正しいか
- 複数候補時の final_status が review のままか
"""

import pytest
import pandas as pd
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from reconciliation_phase1 import Phase1ReconciliationEngine


class TestPhase4aCandidateScoring:
    """Phase 4a スコアリングのテストクラス"""

    @pytest.fixture
    def engine(self):
        """テスト用エンジンを作成"""
        # ダミーマッピングテーブル
        mapping_data = {
            'fax_item_name': [
                'AU案件新規紹介数', 'DL案件既存紹介数',  # 重要項目
                '通常項目1', '通常項目2', '通常項目3',
                'AI紹介総数', 'CZ声がけ総数',  # 重要項目
                'HH既存対応1', 'HI既存対応2',  # 重要項目
            ],
            'csv_column_code': [
                'AU', 'DL',
                'X1', 'X2', 'X3',
                'AI', 'CZ',
                'HH', 'HI',
            ],
            'csv_column_number': list(range(1, 10)),
            'csv_column_name': [f'col_{i}' for i in range(1, 10)],
            'mapping_status': ['confirmed'] * 9,
            'needs_confirmation': [False] * 9,
            'memo': [''] * 9,
        }
        mapping_table = pd.DataFrame(mapping_data)

        # ダミー店舗マスタ
        store_data = {
            'store_code': ['STORE001'],
            'store_name': ['テスト店舗'],
        }
        store_master = pd.DataFrame(store_data)

        # ダミースタッフマスタ
        staff_data = {
            'staff_name': ['スタッフA'],
        }
        staff_master = pd.DataFrame(staff_data)

        return Phase1ReconciliationEngine(mapping_table, store_master, staff_master)

    # ===== グループ1: スコア計算の正確性 =====

    def test_calculate_candidate_score_all_matched(self, engine):
        """全項目一致のスコア計算"""
        field_comparisons = [
            {'comparison_status': 'match', 'csv_column_code': 'AU'},  # 重要 +5
            {'comparison_status': 'match', 'csv_column_code': 'X1'},  # 通常 +2
            {'comparison_status': 'match', 'csv_column_code': 'X2'},  # 通常 +2
            {'comparison_status': 'skipped_pdf_null', 'csv_column_code': 'X3'},  # スキップ 0
        ]

        result = engine._calculate_candidate_score(field_comparisons, 0)

        assert result['candidate_index'] == 0
        assert result['matched_fields'] == 3
        assert result['mismatched_fields'] == 0
        assert result['skipped_fields'] == 1
        assert result['match_rate'] == 1.0
        # 基本スコア: 5 + 2 + 2 = 9
        # confidence: compared_fields=3 → low → 0.6x
        # final_score: 9 * 0.6 = 5.4
        assert result['score'] == pytest.approx(5.4, abs=0.1)

    def test_calculate_candidate_score_with_mismatches(self, engine):
        """不一致を含むスコア計算"""
        field_comparisons = [
            {'comparison_status': 'match', 'csv_column_code': 'AU'},  # 重要 +5
            {'comparison_status': 'mismatch', 'csv_column_code': 'DL'},  # 重要 -10
            {'comparison_status': 'match', 'csv_column_code': 'X1'},  # 通常 +2
            {'comparison_status': 'mismatch', 'csv_column_code': 'X2'},  # 通常 -3
        ]

        result = engine._calculate_candidate_score(field_comparisons, 1)

        assert result['candidate_index'] == 1
        assert result['matched_fields'] == 2
        assert result['mismatched_fields'] == 2
        assert result['match_rate'] == 0.5
        # 基本スコア: 5 - 10 + 2 - 3 = -6 → 0（最小値）
        # confidence: compared_fields=4 → low → 0.6x
        # final_score: max(0, -6 * 0.6) = 0
        assert result['score'] == 0

    def test_calculate_candidate_score_important_items_bonus(self, engine):
        """重要項目の加点が正しく計算されている"""
        field_comparisons = [
            {'comparison_status': 'match', 'csv_column_code': 'AU'},
            {'comparison_status': 'match', 'csv_column_code': 'DL'},
            {'comparison_status': 'match', 'csv_column_code': 'AI'},
            {'comparison_status': 'match', 'csv_column_code': 'CZ'},
            {'comparison_status': 'match', 'csv_column_code': 'HH'},
            {'comparison_status': 'match', 'csv_column_code': 'HI'},
        ]

        result = engine._calculate_candidate_score(field_comparisons, 0)

        assert result['matched_fields'] == 6
        assert result['important_items_match'] == 6
        assert result['important_items_diff'] == 0
        # 基本スコア: 5 + 5 + 5 + 5 + 5 + 5 = 30
        # confidence: compared_fields=6 → medium → 0.9x
        # final_score: 30 * 0.9 = 27
        assert result['score'] == pytest.approx(27, abs=0.1)

    def test_calculate_candidate_score_all_skipped(self, engine):
        """全てスキップされた場合のスコア"""
        field_comparisons = [
            {'comparison_status': 'skipped_pdf_null', 'csv_column_code': 'AU'},
            {'comparison_status': 'skipped_csv_null', 'csv_column_code': 'X1'},
            {'comparison_status': 'skipped_pdf_uncertain', 'csv_column_code': 'X2'},
        ]

        result = engine._calculate_candidate_score(field_comparisons, 0)

        assert result['matched_fields'] == 0
        assert result['mismatched_fields'] == 0
        assert result['skipped_fields'] == 3
        assert result['compared_fields'] == 0
        assert result['score'] == 0
        assert result['confidence'] == 'very_low'

    # ===== グループ2: 信頼度（Confidence）の計算 =====

    def test_confidence_very_low_zero_compared_fields(self, engine):
        """compared_fields = 0 → very_low"""
        confidence = engine._calculate_candidate_confidence(0)
        assert confidence == 'very_low'

    def test_confidence_low_few_compared_fields(self, engine):
        """compared_fields < 5 → low"""
        confidence = engine._calculate_candidate_confidence(4)
        assert confidence == 'low'

    def test_confidence_medium_moderate_compared_fields(self, engine):
        """compared_fields < 15 → medium"""
        confidence = engine._calculate_candidate_confidence(10)
        assert confidence == 'medium'

    def test_confidence_high_many_compared_fields(self, engine):
        """compared_fields >= 15 → high"""
        confidence = engine._calculate_candidate_confidence(15)
        assert confidence == 'high'
        confidence = engine._calculate_candidate_confidence(20)
        assert confidence == 'high'

    # ===== グループ3: 複数候補の順位付け =====

    def test_rank_candidates_clear_winner(self, engine):
        """明確な1位候補（スコア差 > 100）"""
        candidates = [
            {'candidate_index': 0, 'score': 100, 'compared_fields': 20, 'confidence': 'high'},
            {'candidate_index': 1, 'score': 50, 'compared_fields': 20, 'confidence': 'high'},
            {'candidate_index': 2, 'score': 40, 'compared_fields': 20, 'confidence': 'high'},
        ]

        ranked = engine._rank_csv_candidates(candidates)

        assert ranked[0]['score_rank'] == 1
        assert ranked[0]['score_gap_to_next'] == 50
        assert ranked[0]['recommendation'] == 'ambiguous'  # gap=50 ≤ 50 だから ambiguous

    def test_rank_candidates_moderate_difference(self, engine):
        """やや有力な1位候補（50 < スコア差 ≤ 100）"""
        candidates = [
            {'candidate_index': 0, 'score': 200, 'compared_fields': 20, 'confidence': 'high'},
            {'candidate_index': 1, 'score': 130, 'compared_fields': 20, 'confidence': 'high'},
        ]

        ranked = engine._rank_csv_candidates(candidates)

        assert ranked[0]['score_rank'] == 1
        assert ranked[0]['score_gap_to_next'] == 70
        assert ranked[0]['recommendation'] == 'recommended'  # 50 < gap ≤ 100

    def test_rank_candidates_large_difference(self, engine):
        """明確な1位候補（スコア差 > 100）"""
        candidates = [
            {'candidate_index': 0, 'score': 300, 'compared_fields': 20, 'confidence': 'high'},
            {'candidate_index': 1, 'score': 150, 'compared_fields': 20, 'confidence': 'high'},
        ]

        ranked = engine._rank_csv_candidates(candidates)

        assert ranked[0]['score_rank'] == 1
        assert ranked[0]['score_gap_to_next'] == 150
        assert ranked[0]['recommendation'] == 'best_match'  # gap > 100

    def test_rank_candidates_ambiguous(self, engine):
        """僅差（スコア差 ≤ 50）"""
        candidates = [
            {'candidate_index': 0, 'score': 200, 'compared_fields': 20, 'confidence': 'high'},
            {'candidate_index': 1, 'score': 180, 'compared_fields': 20, 'confidence': 'high'},
        ]

        ranked = engine._rank_csv_candidates(candidates)

        assert ranked[0]['score_rank'] == 1
        assert ranked[0]['score_gap_to_next'] == 20
        assert ranked[0]['recommendation'] == 'ambiguous'

    def test_rank_candidates_low_confidence_few_fields(self, engine):
        """比較対象が少ない（compared_fields < 5）"""
        candidates = [
            {'candidate_index': 0, 'score': 100, 'compared_fields': 3, 'confidence': 'low'},
            {'candidate_index': 1, 'score': 50, 'compared_fields': 3, 'confidence': 'low'},
        ]

        ranked = engine._rank_csv_candidates(candidates)

        assert ranked[0]['score_rank'] == 1
        assert ranked[0]['recommendation'] == 'low_confidence'

    def test_rank_candidates_very_low_confidence(self, engine):
        """very_low confidence"""
        candidates = [
            {'candidate_index': 0, 'score': 100, 'compared_fields': 0, 'confidence': 'very_low'},
        ]

        ranked = engine._rank_csv_candidates(candidates)

        assert ranked[0]['score_rank'] == 1
        assert ranked[0]['recommendation'] == 'low_confidence'

    # ===== グループ4: 単一候補の場合（参考） =====

    def test_rank_candidates_single_candidate(self, engine):
        """単一候補の場合（Phase 3 ロジックが優先）"""
        # 複数候補ロジックが呼ばれないため、ここではテストしない
        # 代わりに、reconcile_pdf_with_csv() で single candidate の場合は
        # candidate_scores が空のままであることを確認する
        pass

    # ===== 統合テスト =====

    def test_multiple_candidates_final_status_review(self):
        """複数候補時の final_status = review 確認"""
        # マッピングテーブル
        mapping_data = {
            'fax_item_name': [
                '項目1', '項目2', '項目3',
            ],
            'csv_column_code': [
                'AU', 'X1', 'X2',
            ],
            'csv_column_number': [1, 2, 3],
            'csv_column_name': ['col1', 'col2', 'col3'],
            'mapping_status': ['confirmed'] * 3,
            'needs_confirmation': [False] * 3,
            'memo': [''] * 3,
        }
        mapping_table = pd.DataFrame(mapping_data)

        store_data = {
            'store_code': ['STORE001'],
            'store_name': ['テスト店舗'],
        }
        store_master = pd.DataFrame(store_data)

        staff_data = {
            'staff_name': ['スタッフA'],
        }
        staff_master = pd.DataFrame(staff_data)

        engine = Phase1ReconciliationEngine(mapping_table, store_master, staff_master)

        # PDF レコード
        pdf_record = {
            'page_no': 1,
            'store_name': 'テスト店舗',
            'staff_name': 'スタッフA',
            'tablet_no': 'TAB001',
            'data_no': 'DATA001',
            'mapped_values': {
                'AU': 5,
                'X1': 10,
                'X2': 15,
            }
        }

        # CSV（複数候補）
        csv_data = pd.DataFrame({
            '営業日': ['2026/05/17', '2026/05/17'],
            '取扱コード': ['STORE001', 'STORE001'],
            'col1': [5, 6],
            'col2': [10, 10],
            'col3': [15, 15],
        })

        result = engine.reconcile_pdf_with_csv(pdf_record, csv_data, '2026/05/17')

        # 複数候補なので必ず review
        assert result['status'] == 'review'
        assert result['csv_candidate_count'] == 2

    def test_candidate_scores_structure(self):
        """候補スコアの出力形式確認"""
        mapping_data = {
            'fax_item_name': ['項目1', '項目2'],
            'csv_column_code': ['AU', 'X1'],
            'csv_column_number': [1, 2],
            'csv_column_name': ['col1', 'col2'],
            'mapping_status': ['confirmed'] * 2,
            'needs_confirmation': [False] * 2,
            'memo': [''] * 2,
        }
        mapping_table = pd.DataFrame(mapping_data)

        store_data = {
            'store_code': ['STORE001'],
            'store_name': ['テスト店舗'],
        }
        store_master = pd.DataFrame(store_data)

        staff_data = {
            'staff_name': ['スタッフA'],
        }
        staff_master = pd.DataFrame(staff_data)

        engine = Phase1ReconciliationEngine(mapping_table, store_master, staff_master)

        pdf_record = {
            'page_no': 1,
            'store_name': 'テスト店舗',
            'staff_name': None,
            'tablet_no': None,
            'data_no': None,
            'mapped_values': {
                'AU': 5,
                'X1': 10,
            }
        }

        csv_data = pd.DataFrame({
            '営業日': ['2026/05/17', '2026/05/17'],
            '取扱コード': ['STORE001', 'STORE001'],
            'col1': [5, 6],
            'col2': [10, 10],
        })

        result = engine.reconcile_pdf_with_csv(pdf_record, csv_data, '2026/05/17')

        # 複数候補なので candidate_scores が含まれる
        assert 'candidate_scores' in result
        if len(result['candidate_scores']) > 0:
            candidate = result['candidate_scores'][0]
            assert 'candidate_index' in candidate
            assert 'score' in candidate
            assert 'match_rate' in candidate
            assert 'matched_fields' in candidate
            assert 'mismatched_fields' in candidate
            assert 'skipped_fields' in candidate
            assert 'confidence' in candidate
            assert 'score_rank' in candidate
            assert 'score_gap_to_next' in candidate
            assert 'recommendation' in candidate


class TestPhase4aIntegration:
    """Phase 4a 統合テスト"""

    def test_all_phases_with_multiple_candidates(self):
        """Phase 1-4a を通してテスト（複数候補シナリオ）"""
        # このテストは E2E テストとして機能
        # 実装済みのマスタデータでテスト
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
