"""
Phase 1 最小照合ロジック

目的: PDF 1ページ と CSV行 の照合
方針: スコア計算で候補順位付けし、保守的に「要確認」に分類

禁止事項:
- 日報Noを照合キーにしない
- タブレットNoをCSV直接キーにしない
- スタッフ名をCSV直接キーにしない
- CSV複数行を合算しない
- PDF複数ページを合算しない
- item 28を使わない
"""

import pandas as pd
from typing import Dict, List, Optional, Tuple
from datetime import datetime


class Phase1ReconciliationEngine:
    """Phase 1 最小照合エンジン"""

    def __init__(self, mapping_table: pd.DataFrame, store_master: pd.DataFrame, staff_master: pd.DataFrame):
        """初期化

        Args:
            mapping_table: PDF×CSV列対応マスタ
            store_master: 店舗マスタ
            staff_master: スタッフマスタ
        """
        self.mapping_table = mapping_table
        self.store_master = store_master
        self.staff_master = staff_master

        # Phase 1対象項目の厳しい抽出条件
        # 以下をすべて満たす項目のみを対象
        confirmed = mapping_table[mapping_table['mapping_status'] == 'confirmed'].copy()

        # needs_confirmation = false（文字列または bool）
        confirmed = confirmed[
            (confirmed['needs_confirmation'].astype(str).str.lower() == 'false') |
            (confirmed['needs_confirmation'] == False)
        ]

        # csv_column_code が空欄ではない
        confirmed = confirmed[confirmed['csv_column_code'].notna()]
        confirmed = confirmed[confirmed['csv_column_code'].astype(str).str.strip() != '']

        # item 28（コースアップ→5G→10G）を除外
        confirmed = confirmed[~confirmed['fax_item_name'].astype(str).str.contains('コースアップ', na=False)]

        # memo に除外キーワードが含まれていないか確認
        exclude_keywords = ['未使用', '要確認', '名称確認待ち', '運用確認要', '正式名称確認要']
        for keyword in exclude_keywords:
            confirmed = confirmed[~confirmed['memo'].astype(str).str.contains(keyword, na=False)]

        self.confirmed_mapping = confirmed

    def reconcile_pdf_with_csv(
        self,
        pdf_record: Dict,
        csv_target: pd.DataFrame,
        target_date: str
    ) -> Dict:
        """PDF 1ページ と CSV行 を照合

        Args:
            pdf_record: PDF抽出結果
                {
                    'page_no': int,
                    'store_name': str or None,
                    'staff_name': str or None,
                    'tablet_no': str or None,
                    'data_no': str or None,
                    'mapped_values': {item_code: value, ...}  # マッピング確定済み項目のみ
                }
            csv_target: 対象営業日でフィルタしたCSV
            target_date: 対象営業日（YYYY/MM/DD形式）

        Returns:
            {
                'status': 'match' | 'mismatch' | 'review',
                'csv_record_idx': int or None,
                'candidates': [{'idx': int, 'score': float, ...}, ...],
                'best_match': {'idx': int, 'score': float, ...} or None,
                'score': float,
                'match_count': int,
                'diff_count': int,
                'unreadable_count': int,
                'matched_items': [str, ...],
                'diff_items': [str, ...],
                'unreadable_items': [str, ...],
                'warnings': [str, ...],
                'store_code': str,
                'store_name': str,
                'staff_name': str or None,
                'tablet_no': str or None,
                'data_no': str,
                'review_reasons': [str, ...]
            }
        """

        warnings = []
        review_reasons = []

        # Step 0: mapped_values チェック（Phase 6B実装待ち）
        pdf_values = pdf_record.get('mapped_values', {})
        if not pdf_values or len(pdf_values) == 0:
            warnings.append("PDF numeric items not extracted (Phase 6B pending)")
            review_reasons.append("No numeric items for detailed reconciliation (PDF extraction Phase 6B not yet implemented)")

        # Step 1: 店舗候補を特定（PDF店舗名から）
        store_code, store_name_normalized, store_match_confidence = self._find_store_code(
            pdf_record.get('store_name'),
            warnings
        )

        # Step 2: CSV候補行を抽出（店舗コードで）
        candidates_df = self._find_csv_candidates(
            store_code,
            csv_target,
            target_date,
            review_reasons
        )

        # Step 3: 候補行が見つからない場合
        if candidates_df.empty:
            return self._create_review_result(
                pdf_record,
                store_code,
                store_name_normalized,
                "No CSV candidates found",
                warnings,
                review_reasons
            )

        # Step 4: 各候補行のスコアを計算
        candidates_with_scores = []
        for idx, csv_row in candidates_df.iterrows():
            score_result = self._calculate_score(
                pdf_record,
                csv_row,
                store_match_confidence,
                warnings
            )
            score_result['csv_idx'] = idx
            candidates_with_scores.append(score_result)

        # スコア順ソート
        candidates_with_scores.sort(key=lambda x: x['total_score'], reverse=True)
        best_match = candidates_with_scores[0]

        # Step 5: ステータス判定（保守的に）
        status = self._determine_status(
            best_match,
            len(candidates_with_scores),
            pdf_record,
            review_reasons,
            warnings
        )

        return {
            'status': status,
            'csv_record_idx': int(best_match['csv_idx']),
            'candidates': candidates_with_scores[:3],  # 上位3件のみ
            'best_match': best_match,
            'score': best_match['total_score'],
            'match_count': best_match['match_count'],
            'diff_count': best_match['diff_count'],
            'unreadable_count': best_match['unreadable_count'],
            'matched_items': best_match['matched_items'],
            'diff_items': best_match['diff_items'],
            'unreadable_items': best_match['unreadable_items'],
            'warnings': warnings,
            'store_code': store_code,
            'store_name': store_name_normalized,
            'staff_name': pdf_record.get('staff_name'),
            'tablet_no': pdf_record.get('tablet_no'),
            'data_no': pdf_record.get('data_no'),
            'review_reasons': review_reasons
        }

    def _find_store_code(self, pdf_store_name: Optional[str], warnings: List[str]) -> Tuple[Optional[str], Optional[str], float]:
        """PDF店舗名から店舗コード候補を特定"""

        if not pdf_store_name or str(pdf_store_name).strip() == '':
            warnings.append("Store name not readable from PDF")
            return None, None, 0.0

        # 店舗名正規化
        pdf_store_normalized = self._normalize_text(pdf_store_name)

        # 店舗マスタと照合
        for idx, row in self.store_master.iterrows():
            master_name_normalized = self._normalize_text(row['store_name'])
            if pdf_store_normalized == master_name_normalized:
                return row['store_code'], row['store_name'], 1.0  # 完全一致

            # 部分一致も検討
            if pdf_store_normalized in master_name_normalized or master_name_normalized in pdf_store_normalized:
                return row['store_code'], row['store_name'], 0.8  # 部分一致

        warnings.append(f"Store name not found in master: {pdf_store_name}")
        return None, pdf_store_name, 0.3

    def _find_csv_candidates(
        self,
        store_code: Optional[str],
        csv_target: pd.DataFrame,
        target_date: str,
        review_reasons: List[str]
    ) -> pd.DataFrame:
        """CSV候補行を抽出"""

        if not store_code:
            review_reasons.append("Store code could not be determined from PDF")
            return pd.DataFrame()

        # CSV列281「法人・店舗(取扱コード)」で検索
        # 列名は環境に応じて異なる可能性あり
        store_col = None
        for col in csv_target.columns:
            if 'コード' in str(col) or '取扱' in str(col) or col == 281 or col == '法人・店舗(取扱コード)':
                store_col = col
                break

        if store_col is None:
            # デフォルトで列281を使用
            if 281 - 1 < len(csv_target.columns):
                store_col = csv_target.columns[280]  # 0-indexed

        if store_col is None:
            review_reasons.append("Store code column not found in CSV")
            return pd.DataFrame()

        # 店舗コードで候補を絞る
        candidates = csv_target[csv_target.iloc[:, 280] == store_code]

        if len(candidates) > 1:
            review_reasons.append(f"Multiple CSV candidates found ({len(candidates)} rows)")

        return candidates

    def _calculate_score(
        self,
        pdf_record: Dict,
        csv_row: pd.Series,
        store_match_confidence: float,
        warnings: List[str]
    ) -> Dict:
        """スコア計算"""

        score_result = {
            'base_score': 0,
            'match_count': 0,
            'diff_count': 0,
            'unreadable_count': 0,
            'matched_items': [],
            'diff_items': [],
            'unreadable_items': [],
            'bonus_store': 200 * store_match_confidence,  # 店舗一致: 200点
            'bonus_staff': 0,
            'total_score': 0
        }

        # Step 1: マッピング済み数値項目の比較
        pdf_values = pdf_record.get('mapped_values', {})

        for idx, mapping_row in self.confirmed_mapping.iterrows():
            item_name = mapping_row.get('fax_item_name', '')
            csv_col = mapping_row.get('csv_column_number')

            if pd.isna(csv_col) or csv_col >= len(csv_row):
                score_result['unreadable_count'] += 1
                score_result['unreadable_items'].append(item_name)
                continue

            # CSV値を取得
            csv_val = csv_row.iloc[int(csv_col) - 1] if csv_col > 0 else None

            # PDF値を取得
            item_code = mapping_row.get('csv_column_code', '')
            pdf_val = pdf_values.get(item_code)

            # 値が読める場合のみ比較
            if pdf_val is not None:
                try:
                    pdf_num = int(float(str(pdf_val).replace(',', '')))
                    csv_num = int(float(str(csv_val).replace(',', ''))) if csv_val is not None else 0

                    if pdf_num == csv_num:
                        score_result['base_score'] += 10
                        score_result['match_count'] += 1
                        score_result['matched_items'].append(item_name)
                    else:
                        score_result['base_score'] -= 5
                        score_result['diff_count'] += 1
                        score_result['diff_items'].append(f"{item_name}(PDF:{pdf_num} vs CSV:{csv_num})")
                except (ValueError, TypeError):
                    score_result['unreadable_count'] += 1
                    score_result['unreadable_items'].append(item_name)
            else:
                score_result['unreadable_count'] += 1
                score_result['unreadable_items'].append(item_name)

        # Step 2: スタッフ名補助情報
        pdf_staff = pdf_record.get('staff_name')
        if pdf_staff and str(pdf_staff).strip():
            if pdf_staff in self.staff_master['staff_name'].values:
                score_result['bonus_staff'] = 2

        # Step 3: 合計スコア
        score_result['total_score'] = (
            score_result['base_score'] +
            score_result['bonus_store'] +
            score_result['bonus_staff']
        )

        return score_result

    def _determine_status(
        self,
        best_match: Dict,
        candidates_count: int,
        pdf_record: Dict,
        review_reasons: List[str],
        warnings: List[str]
    ) -> str:
        """ステータス判定（保守的に）

        一致の条件:
        - CSV候補が1件 AND
        - 店舗コード候補が明確 AND
        - 照合対象の主要数値項目に不一致がない AND
        - 読取不可が少ない AND
        - 要確認項目がない、または軽微

        要確認の条件（以下のいずれか）:
        - 候補CSV行が複数ある
        - 候補スコアが近い
        - 一致項目と不一致項目が混在している
        - PDF読取不可が多い
        - PDF上の店舗名が読めない
        - CSV列対応が未確定
        - その他の不確定な状況
        """

        # 複数候補 → 必ず要確認
        if candidates_count > 1:
            review_reasons.append(f"Multiple CSV candidates ({candidates_count})")
            return "review"

        # 店舗コード候補が見つからない → 必ず要確認
        if pdf_record.get('store_name') is None or not str(pdf_record.get('store_name')).strip():
            review_reasons.append("Store name not readable from PDF")
            return "review"

        # 読取不可が多い → 要確認
        if best_match['unreadable_count'] > 3:
            review_reasons.append(f"Too many unreadable items ({best_match['unreadable_count']})")
            return "review"

        # 一致項目と不一致項目が混在 → 要確認
        if best_match['match_count'] > 0 and best_match['diff_count'] > 0:
            review_reasons.append(f"Mixed match/diff ({best_match['match_count']} match, {best_match['diff_count']} diff)")
            return "review"

        # PDF読取警告が多い → 要確認
        if len(warnings) > 2:
            review_reasons.append(f"Multiple reading warnings ({len(warnings)})")
            return "review"

        # 主要照合対象項目がない → 要確認
        if best_match['match_count'] == 0 and best_match['unreadable_count'] == 0 and best_match['diff_count'] == 0:
            review_reasons.append("No items to reconcile")
            return "review"

        # 明確な不一致 → 不一致
        if best_match['diff_count'] > 0:
            return "mismatch"

        # 一致の厳しい条件
        # - 不一致がない
        # - 読取不可が少ない（0～1程度）
        # - 一致項目がある
        if best_match['diff_count'] == 0 and best_match['unreadable_count'] <= 1 and best_match['match_count'] > 0:
            return "match"

        # それ以外は要確認（保守的）
        review_reasons.append("Insufficient confidence in reconciliation")
        return "review"

    def _create_review_result(
        self,
        pdf_record: Dict,
        store_code: Optional[str],
        store_name: Optional[str],
        reason: str,
        warnings: List[str],
        review_reasons: List[str]
    ) -> Dict:
        """要確認結果を作成"""

        return {
            'status': 'review',
            'csv_record_idx': None,
            'candidates': [],
            'best_match': None,
            'score': 0,
            'match_count': 0,
            'diff_count': 0,
            'unreadable_count': 0,
            'matched_items': [],
            'diff_items': [],
            'unreadable_items': [],
            'warnings': warnings,
            'store_code': store_code,
            'store_name': store_name,
            'staff_name': pdf_record.get('staff_name'),
            'tablet_no': pdf_record.get('tablet_no'),
            'data_no': pdf_record.get('data_no'),
            'review_reasons': review_reasons + [reason]
        }

    def _normalize_text(self, text: str) -> str:
        """テキスト正規化"""
        if not text:
            return ""
        import unicodedata
        # 全角→半角
        text = unicodedata.normalize('NFKC', str(text))
        # 空白削除
        text = text.replace(' ', '').replace('　', '')
        # 大文字小文字統一
        text = text.upper()
        return text


# ===== ヘルパー関数 =====

def create_phase1_engine(
    mapping_table_path: str,
    store_master_path: str,
    staff_master_path: str
) -> Phase1ReconciliationEngine:
    """Phase 1エンジンを生成"""

    mapping_table = pd.read_csv(mapping_table_path)
    store_master = pd.read_csv(store_master_path)
    staff_master = pd.read_csv(staff_master_path)

    return Phase1ReconciliationEngine(mapping_table, store_master, staff_master)
