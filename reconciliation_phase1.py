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
import re
import unicodedata


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

        # Step 2: CSV候補行を抽出（日付 + 店舗コードで）
        csv_match_result = self._find_csv_candidates(
            store_code,
            csv_target,
            target_date,
            review_reasons
        )
        candidates_df = csv_match_result['candidates_df']

        # Step 3: 候補行が見つからない場合
        if candidates_df.empty:
            return self._create_review_result(
                pdf_record,
                store_code,
                store_name_normalized,
                csv_match_result['match_status'],
                csv_match_result.get('normalized_date'),
                warnings,
                review_reasons
            )

        # Step 4: Phase 3 - confirmed項目のPDF値とCSV値を比較
        best_csv_row = csv_match_result['best_match']
        comparison_result = self._compare_fields(
            pdf_record,
            best_csv_row,
            csv_match_result
        )

        # Step 5: Phase 3 - ステータス判定
        phase3_status = self._determine_phase3_status(
            csv_match_result,
            comparison_result,
            review_reasons
        )

        # Step 6: 既存ロジック互換のため、各候補行のスコアを計算
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

        # Step 7: 最終ステータス判定（Phase 3 を優先）
        status = phase3_status

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
            'review_reasons': review_reasons,
            # Phase 3 新規項目
            'field_comparisons': comparison_result['field_comparisons'],
            'field_comparison_summary': comparison_result['summary'],
            'phase3_status': phase3_status,
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
    ) -> Dict:
        """CSV候補行を抽出（日付 + 店舗コード で検索）

        Returns: {
            'match_status': 'candidate_found' | 'no_csv_candidate' | 'multiple_csv_candidates',
            'csv_candidate_count': int,
            'candidates_df': DataFrame,
            'best_match': pd.Series or None,
            'normalized_date': str,
            'date_normalized_status': 'success' | 'failed'
        }
        """
        result = {
            'match_status': 'no_csv_candidate',
            'csv_candidate_count': 0,
            'candidates_df': pd.DataFrame(),
            'best_match': None,
            'normalized_date': None,
            'date_normalized_status': 'failed'
        }

        # Step 1: store_code チェック
        if not store_code:
            review_reasons.append("Store code could not be determined from PDF")
            return result

        # Step 2: 日付を正規化
        normalized_date, date_status = self._normalize_date(target_date)
        result['normalized_date'] = normalized_date
        result['date_normalized_status'] = date_status

        if date_status == 'failed':
            review_reasons.append(f"Failed to normalize PDF date: {target_date}")
            return result

        # Step 3: CSV 日付列を検出
        date_col = self._detect_date_column(csv_target)
        if date_col is None:
            review_reasons.append("Date column not found in CSV")
            return result

        # Step 4: CSV 店舗コード列を検出
        store_col_idx = self._detect_store_code_column_index(csv_target)
        if store_col_idx is None:
            review_reasons.append("Store code column not found in CSV")
            return result

        # Step 5: 日付で絞り込み
        try:
            # CSV 日付を正規化して比較
            csv_target_copy = csv_target.copy()
            csv_target_copy['normalized_csv_date'] = csv_target_copy[date_col].apply(
                lambda x: self._normalize_date(x)[0]
            )

            date_filtered = csv_target_copy[csv_target_copy['normalized_csv_date'] == normalized_date]

            if date_filtered.empty:
                review_reasons.append(f"No CSV candidates found for date: {target_date}")
                return result
        except Exception as e:
            review_reasons.append(f"Error filtering by date: {str(e)}")
            return result

        # Step 6: 店舗コードで絞り込み
        try:
            store_filtered = date_filtered[
                date_filtered.iloc[:, store_col_idx] == store_code
            ]

            if store_filtered.empty:
                review_reasons.append(f"No CSV candidates found for store_code: {store_code} and date: {target_date}")
                return result

            # 正規化列を削除して返す
            candidates_df = store_filtered.drop(columns=['normalized_csv_date'])

        except Exception as e:
            review_reasons.append(f"Error filtering by store_code: {str(e)}")
            return result

        # Step 7: 候補数で分類
        candidate_count = len(candidates_df)

        if candidate_count == 1:
            result['match_status'] = 'candidate_found'
            result['csv_candidate_count'] = 1
            result['candidates_df'] = candidates_df
            result['best_match'] = candidates_df.iloc[0]

        elif candidate_count > 1:
            result['match_status'] = 'multiple_csv_candidates'
            result['csv_candidate_count'] = candidate_count
            result['candidates_df'] = candidates_df
            # 複数候補の場合は複数行を保持
            review_reasons.append(f"Multiple CSV candidates found ({candidate_count} rows) for store_code={store_code} and date={target_date}")

        return result

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
        match_status: str,
        pdf_date: Optional[str],
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
            'pdf_page_number': pdf_record.get('page_no'),
            'pdf_date': pdf_date,
            'pdf_store_name': pdf_record.get('store_name'),
            'mapped_store_code': store_code,
            'store_code_mapping_status': 'exact_match' if store_code else 'not_found',
            'match_status': match_status,
            'csv_candidate_count': 0,
            'csv_candidate_rows': [],
            'review_reasons': review_reasons
        }

    def _normalize_text(self, text: str) -> str:
        """テキスト正規化"""
        if not text:
            return ""
        # 全角→半角
        text = unicodedata.normalize('NFKC', str(text))
        # 空白削除
        text = text.replace(' ', '').replace('　', '')
        # 大文字小文字統一
        text = text.upper()
        return text

    def _normalize_date(self, date_input: Optional[str]) -> Tuple[Optional[str], str]:
        """日付を YYYY/MM/DD に正規化

        対応形式:
        - 2026/05/17
        - 2026-05-17
        - 2026年5月17日
        - pandas Timestamp / datetime

        Returns: (normalized_date: str, status: 'success' | 'failed')
            normalized_date は YYYY/MM/DD 形式、失敗時は None
        """

        if date_input is None:
            return None, 'failed'

        # pandas Timestamp または datetime の場合
        if isinstance(date_input, pd.Timestamp):
            try:
                return f"{date_input.year:04d}/{date_input.month:02d}/{date_input.day:02d}", 'success'
            except:
                return None, 'failed'

        if isinstance(date_input, datetime):
            try:
                return f"{date_input.year:04d}/{date_input.month:02d}/{date_input.day:02d}", 'success'
            except:
                return None, 'failed'

        # 文字列の場合
        date_str = str(date_input).strip()

        if not date_str:
            return None, 'failed'

        # パターン1: YYYY/MM/DD （既に正規化済み）
        match = re.match(r'(\d{4})/(\d{1,2})/(\d{1,2})', date_str)
        if match:
            try:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                return f"{year:04d}/{month:02d}/{day:02d}", 'success'
            except:
                return None, 'failed'

        # パターン2: YYYY-MM-DD
        match = re.match(r'(\d{4})-(\d{1,2})-(\d{1,2})', date_str)
        if match:
            try:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                return f"{year:04d}/{month:02d}/{day:02d}", 'success'
            except:
                return None, 'failed'

        # パターン3: YYYY年M月D日 または YYYY年MM月DD日
        match = re.match(r'(\d{4})年(\d{1,2})月(\d{1,2})日', date_str)
        if match:
            try:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                return f"{year:04d}/{month:02d}/{day:02d}", 'success'
            except:
                return None, 'failed'

        # パターン4: MM/DD/YYYY （米国形式）
        match = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})', date_str)
        if match:
            try:
                month, day, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return f"{year:04d}/{month:02d}/{day:02d}", 'success'
            except:
                pass

        # パターン5: YYYYMMDD （区切りなし）
        match = re.match(r'(\d{4})(\d{2})(\d{2})', date_str)
        if match:
            try:
                year, month, day = int(match.group(1)), int(match.group(2)), int(match.group(3))
                if 1 <= month <= 12 and 1 <= day <= 31:
                    return f"{year:04d}/{month:02d}/{day:02d}", 'success'
            except:
                pass

        # いずれにも該当しない
        return None, 'failed'

    def _detect_date_column(self, csv_target: pd.DataFrame) -> Optional[str]:
        """CSV 日付列を検出"""

        # パターン1: 列名に「営業日」「日付」を含む
        for col in csv_target.columns:
            col_str = str(col).lower()
            if '営業日' in str(col) or '日付' in str(col):
                return col

        # パターン2: 列 A（最初の列）を試す
        if len(csv_target.columns) > 0:
            return csv_target.columns[0]

        return None

    def _detect_store_code_column_index(self, csv_target: pd.DataFrame) -> Optional[int]:
        """CSV 店舗コード列のインデックスを検出（0-indexed）"""

        # パターン1: 列名に「取扱」「コード」を含む
        for idx, col in enumerate(csv_target.columns):
            col_str = str(col)
            if '取扱' in col_str and 'コード' in col_str:
                return idx

        # パターン2: 列 JU（281番目、0-indexed: 280）を試す
        if len(csv_target.columns) > 280:
            return 280

        # パターン3: 列 281（1-indexed）の場合
        if len(csv_target.columns) >= 281:
            return 280

        return None

    def _normalize_numeric_value(self, value: Optional[object]) -> Optional[int]:
        """数値を正規化（int に統一）

        Args:
            value: 入力値（int, float, str, None など）

        Returns:
            正規化済み数値、または None
        """

        if value is None:
            return None

        if isinstance(value, bool):
            # bool は int の subclass なので先に check
            return None

        if isinstance(value, (int, float)):
            try:
                return int(value)
            except (ValueError, TypeError):
                return None

        if isinstance(value, str):
            # 文字列の場合、数値化を試みる
            if not value or value.strip() == '':
                return None

            # カンマを削除
            clean_str = str(value).replace(',', '').strip()

            try:
                return int(float(clean_str))
            except (ValueError, TypeError):
                return None

        # pandas.NA, NaN, etc.
        if pd.isna(value):
            return None

        return None

    def _compare_fields(
        self,
        pdf_record: Dict,
        csv_row: pd.Series,
        csv_match_result: Dict
    ) -> Dict:
        """確定済み項目のPDF値とCSV値を比較

        Args:
            pdf_record: PDF抽出結果
            csv_row: CSV行データ（Series）
            csv_match_result: Phase 2 の結果

        Returns:
            {
                'field_comparisons': [
                    {
                        'fax_item_name': str,
                        'csv_column_code': str,
                        'csv_column_name': str,
                        'csv_column_number': int,
                        'pdf_value': any,
                        'csv_value': any,
                        'pdf_value_status': 'confirmed' | 'uncertain' | 'null',
                        'csv_value_status': 'confirmed' | 'null',
                        'comparison_status': 'match' | 'mismatch' | 'skipped_*',
                        'reason': str,
                    },
                    ...
                ],
                'summary': {
                    'total_fields': int,
                    'compared_fields': int,
                    'matched_fields': int,
                    'mismatched_fields': int,
                    'skipped_fields': int,
                    'match_rate': float,
                    'needs_review_count': int,
                }
            }
        """

        field_comparisons = []
        matched_count = 0
        mismatched_count = 0
        skipped_count = 0

        pdf_mapped_values = pdf_record.get('mapped_values', {})

        # self.confirmed_mapping から各項目を取得
        for idx, mapping_row in self.confirmed_mapping.iterrows():
            item_name = mapping_row.get('fax_item_name', '')
            csv_column_code = mapping_row.get('csv_column_code', '')
            csv_column_number = mapping_row.get('csv_column_number')

            # Step 1: csv_column_number チェック
            if pd.isna(csv_column_number):
                field_comparisons.append({
                    'fax_item_name': item_name,
                    'csv_column_code': csv_column_code,
                    'csv_column_name': mapping_row.get('csv_column_name', ''),
                    'csv_column_number': None,
                    'pdf_value': None,
                    'csv_value': None,
                    'pdf_value_status': 'null',
                    'csv_value_status': 'null',
                    'comparison_status': 'skipped_no_csv_column',
                    'reason': 'CSV column number not found',
                })
                skipped_count += 1
                continue

            # Step 2: PDF値を取得
            pdf_value = pdf_mapped_values.get(csv_column_code)
            pdf_value_status = 'null'

            if pdf_value is None:
                pdf_value_status = 'null'
            elif pdf_value == 'uncertain':
                pdf_value_status = 'uncertain'
            elif isinstance(pdf_value, str) and pdf_value in ['unreadable', 'uncertain']:
                pdf_value_status = pdf_value
            else:
                pdf_value_status = 'confirmed'

            # Step 3: PDF値の判定（比較対象か判定）
            if pdf_value_status == 'null':
                field_comparisons.append({
                    'fax_item_name': item_name,
                    'csv_column_code': csv_column_code,
                    'csv_column_name': mapping_row.get('csv_column_name', ''),
                    'csv_column_number': int(csv_column_number) if not pd.isna(csv_column_number) else None,
                    'pdf_value': None,
                    'csv_value': None,
                    'pdf_value_status': 'null',
                    'csv_value_status': 'null',
                    'comparison_status': 'skipped_pdf_null',
                    'reason': 'PDF value is null',
                })
                skipped_count += 1
                continue

            if pdf_value_status == 'uncertain':
                field_comparisons.append({
                    'fax_item_name': item_name,
                    'csv_column_code': csv_column_code,
                    'csv_column_name': mapping_row.get('csv_column_name', ''),
                    'csv_column_number': int(csv_column_number) if not pd.isna(csv_column_number) else None,
                    'pdf_value': pdf_value,
                    'csv_value': None,
                    'pdf_value_status': 'uncertain',
                    'csv_value_status': 'null',
                    'comparison_status': 'skipped_pdf_uncertain',
                    'reason': 'PDF value is uncertain (tally mark途中形)',
                })
                skipped_count += 1
                continue

            # Step 4: CSV値を取得（1-indexed → 0-indexed）
            try:
                csv_col_idx = int(csv_column_number) - 1

                if csv_col_idx >= len(csv_row) or csv_col_idx < 0:
                    field_comparisons.append({
                        'fax_item_name': item_name,
                        'csv_column_code': csv_column_code,
                        'csv_column_name': mapping_row.get('csv_column_name', ''),
                        'csv_column_number': int(csv_column_number),
                        'pdf_value': pdf_value,
                        'csv_value': None,
                        'pdf_value_status': pdf_value_status,
                        'csv_value_status': 'null',
                        'comparison_status': 'skipped_csv_null',
                        'reason': f'CSV column index {csv_col_idx} out of range',
                    })
                    skipped_count += 1
                    continue

                csv_value = csv_row.iloc[csv_col_idx]

            except (ValueError, TypeError, IndexError):
                field_comparisons.append({
                    'fax_item_name': item_name,
                    'csv_column_code': csv_column_code,
                    'csv_column_name': mapping_row.get('csv_column_name', ''),
                    'csv_column_number': int(csv_column_number) if not pd.isna(csv_column_number) else None,
                    'pdf_value': pdf_value,
                    'csv_value': None,
                    'pdf_value_status': pdf_value_status,
                    'csv_value_status': 'null',
                    'comparison_status': 'skipped_csv_null',
                    'reason': 'CSV column access error',
                })
                skipped_count += 1
                continue

            # Step 5: CSV値の判定
            csv_value_status = 'confirmed'
            if csv_value is None or pd.isna(csv_value) or csv_value == '':
                csv_value_status = 'null'

            # Step 6: 数値正規化と比較
            pdf_normalized = self._normalize_numeric_value(pdf_value)
            csv_normalized = self._normalize_numeric_value(csv_value)

            # Step 7: 値が比較可能かチェック
            if pdf_normalized is None:
                field_comparisons.append({
                    'fax_item_name': item_name,
                    'csv_column_code': csv_column_code,
                    'csv_column_name': mapping_row.get('csv_column_name', ''),
                    'csv_column_number': int(csv_column_number),
                    'pdf_value': pdf_value,
                    'csv_value': csv_value,
                    'pdf_value_status': pdf_value_status,
                    'csv_value_status': csv_value_status,
                    'comparison_status': 'skipped_pdf_null',
                    'reason': 'PDF value cannot be normalized to numeric',
                })
                skipped_count += 1
                continue

            if csv_normalized is None:
                field_comparisons.append({
                    'fax_item_name': item_name,
                    'csv_column_code': csv_column_code,
                    'csv_column_name': mapping_row.get('csv_column_name', ''),
                    'csv_column_number': int(csv_column_number),
                    'pdf_value': pdf_value,
                    'csv_value': csv_value,
                    'pdf_value_status': pdf_value_status,
                    'csv_value_status': csv_value_status,
                    'comparison_status': 'skipped_csv_null',
                    'reason': 'CSV value cannot be normalized to numeric',
                })
                skipped_count += 1
                continue

            # Step 8: 比較
            if pdf_normalized == csv_normalized:
                comparison_status = 'match'
                matched_count += 1
                reason = ''
            else:
                comparison_status = 'mismatch'
                mismatched_count += 1
                reason = f'PDF={pdf_normalized}, CSV={csv_normalized}'

            field_comparisons.append({
                'fax_item_name': item_name,
                'csv_column_code': csv_column_code,
                'csv_column_name': mapping_row.get('csv_column_name', ''),
                'csv_column_number': int(csv_column_number),
                'pdf_value': pdf_value,
                'csv_value': csv_value,
                'pdf_value_status': pdf_value_status,
                'csv_value_status': csv_value_status,
                'comparison_status': comparison_status,
                'reason': reason,
            })

        # Summary を計算
        total_fields = len(self.confirmed_mapping)
        compared_fields = matched_count + mismatched_count
        match_rate = matched_count / compared_fields if compared_fields > 0 else 0.0

        summary = {
            'total_fields': total_fields,
            'compared_fields': compared_fields,
            'matched_fields': matched_count,
            'mismatched_fields': mismatched_count,
            'skipped_fields': skipped_count,
            'match_rate': match_rate,
            'needs_review_count': mismatched_count,
        }

        return {
            'field_comparisons': field_comparisons,
            'summary': summary
        }

    def _determine_phase3_status(
        self,
        csv_match_result: Dict,
        comparison_result: Dict,
        review_reasons: List[str]
    ) -> str:
        """Phase 3 の最終ステータスを判定

        Returns: 'match' | 'mismatch' | 'review'
        """

        # Phase 2 の候補状況確認
        if csv_match_result['match_status'] == 'no_csv_candidate':
            review_reasons.append("No CSV candidates found (Phase 2)")
            return 'review'

        if csv_match_result['match_status'] == 'multiple_csv_candidates':
            review_reasons.append(f"Multiple CSV candidates ({csv_match_result['csv_candidate_count']} rows)")
            return 'review'

        # Phase 3 の比較結果確認
        summary = comparison_result['summary']

        # 比較対象項目がない場合
        if summary['compared_fields'] == 0:
            review_reasons.append(f"No comparable fields ({summary['skipped_fields']} skipped)")
            return 'review'

        # 不一致がない場合→ match
        if summary['mismatched_fields'] == 0 and summary['compared_fields'] > 0:
            return 'match'

        # 不一致がある場合→ mismatch
        if summary['mismatched_fields'] > 0:
            review_reasons.append(f"{summary['mismatched_fields']} mismatched fields")
            return 'mismatch'

        # デフォルト
        review_reasons.append("Insufficient data for reconciliation")
        return 'review'


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
