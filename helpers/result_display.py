"""
Phase 4b: 照合結果確認UI用 Helper関数

目的：
- Phase 1-4a の照合結果をStreamlit表示用にフォーマット
- ページサマリーテーブル、複数候補、フィールド比較を生成
- ダウンロード用CSV生成
"""

import pandas as pd
from typing import List, Dict, Optional, Tuple
import io
from datetime import datetime


def format_page_summary_table(results: List[Dict]) -> pd.DataFrame:
    """Phase 1-4a の結果からページサマリーテーブルを生成

    Args:
        results: reconcile_pdf_with_csv() の返り値のリスト

    Returns:
        表示用DataFrame
    """

    if not results:
        return pd.DataFrame()

    summary_rows = []

    for result in results:
        # Phase 2 の候補状況
        match_status = result.get('match_status', 'unknown')
        csv_candidate_count = result.get('csv_candidate_count', 0)

        # Phase 3 フィールド比較結果
        field_summary = result.get('field_comparison_summary', {})
        compared_fields = field_summary.get('compared_fields', 0)
        matched_fields = field_summary.get('matched_fields', 0)
        mismatched_fields = field_summary.get('mismatched_fields', 0)

        # Match rate 計算
        match_rate = (
            matched_fields / compared_fields
            if compared_fields > 0
            else 0.0
        )

        # Phase 4a スコア情報（複数候補時）
        candidate_scores = result.get('candidate_scores', [])
        recommendation = 'N/A'
        confidence = 'N/A'

        if candidate_scores and len(candidate_scores) > 0:
            best = candidate_scores[0]
            recommendation = best.get('recommendation', 'N/A')
            confidence = best.get('confidence', 'N/A')
        else:
            # 単一候補時は field_comparison_summary から推測
            confidence = 'high' if compared_fields >= 15 else (
                'medium' if compared_fields >= 5 else 'low'
            )

        # Review reasons
        review_reasons = result.get('review_reasons', [])
        review_reason_str = ' | '.join(review_reasons)[:100]

        summary_rows.append({
            'Page': result.get('page_no', 0),
            'Date': result.get('pdf_date', ''),
            'Store': result.get('pdf_store_name', ''),
            'Code': result.get('store_code', ''),
            'Status': result.get('status', 'unknown'),
            'Match Type': match_status,
            'Candidates': csv_candidate_count,
            'Match Rate': f"{match_rate:.1%}",
            'Confidence': confidence,
            'Recommendation': recommendation,
            'Issues': f"{mismatched_fields} mismatch" if mismatched_fields > 0 else "OK",
        })

    return pd.DataFrame(summary_rows)


def format_candidate_scores_table(candidate_scores: List[Dict]) -> Optional[pd.DataFrame]:
    """複数CSV候補のスコア情報をテーブル形式で生成

    Args:
        candidate_scores: candidate_scores リスト（Phase 4a）

    Returns:
        表示用DataFrame、または None（候補なし）
    """

    if not candidate_scores or len(candidate_scores) == 0:
        return None

    candidate_rows = []

    for candidate in candidate_scores:
        candidate_rows.append({
            'Rank': candidate.get('score_rank', 0),
            'Index': candidate.get('candidate_index', 0),
            'Score': f"{candidate.get('score', 0):.1f}",
            'Match Rate': f"{candidate.get('match_rate', 0):.1%}",
            'Confidence': candidate.get('confidence', 'N/A'),
            'Matched': candidate.get('matched_fields', 0),
            'Mismatched': candidate.get('mismatched_fields', 0),
            'Skipped': candidate.get('skipped_fields', 0),
            'Recommendation': candidate.get('recommendation', 'N/A'),
        })

    return pd.DataFrame(candidate_rows)


def format_field_comparison_table(field_comparisons: List[Dict]) -> Optional[pd.DataFrame]:
    """フィールド比較詳細をテーブル形式で生成

    Args:
        field_comparisons: Phase 3 の field_comparisons リスト

    Returns:
        表示用DataFrame、または None（比較なし）
    """

    if not field_comparisons:
        return None

    comparison_rows = []

    for comp in field_comparisons:
        comparison_status = comp.get('comparison_status', '')

        # PDF値・CSV値のフォーマット
        pdf_value = comp.get('pdf_value')
        csv_value = comp.get('csv_value')

        # null / uncertain の場合は表示を整える
        if pdf_value is None:
            pdf_value_str = '-'
        elif pdf_value == 'uncertain':
            pdf_value_str = '(要確認)'
        else:
            pdf_value_str = str(pdf_value)

        if csv_value is None:
            csv_value_str = '-'
        else:
            csv_value_str = str(csv_value)

        # Status 日本語化
        status_map = {
            'match': '✅ match',
            'mismatch': '❌ mismatch',
            'skipped_pdf_null': '⏭️ skipped (PDF null)',
            'skipped_pdf_uncertain': '⏭️ skipped (PDF uncertain)',
            'skipped_csv_null': '⏭️ skipped (CSV null)',
            'skipped_no_csv_column': '⏭️ skipped (no column)',
        }
        status_str = status_map.get(comparison_status, comparison_status)

        comparison_rows.append({
            'Item': comp.get('fax_item_name', ''),
            'Column': comp.get('csv_column_code', ''),
            'CSV Column Name': comp.get('csv_column_name', ''),
            'PDF Value': pdf_value_str,
            'CSV Value': csv_value_str,
            'Status': status_str,
            'Reason': comp.get('reason', ''),
        })

    return pd.DataFrame(comparison_rows)


def generate_download_csv(results: List[Dict]) -> Tuple[bytes, str]:
    """ダウンロード用CSV（ページサマリー）を生成

    Args:
        results: reconcile_pdf_with_csv() の返り値のリスト

    Returns:
        (CSV bytes, filename) タプル
    """

    if not results:
        return b'', f"reconciliation_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    summary_rows = []

    for result in results:
        # Phase 2 の候補状況
        match_status = result.get('match_status', 'unknown')
        csv_candidate_count = result.get('csv_candidate_count', 0)

        # Phase 3 フィールド比較結果
        field_summary = result.get('field_comparison_summary', {})
        compared_fields = field_summary.get('compared_fields', 0)
        matched_fields = field_summary.get('matched_fields', 0)
        mismatched_fields = field_summary.get('mismatched_fields', 0)

        # Match rate 計算
        match_rate = (
            matched_fields / compared_fields
            if compared_fields > 0
            else 0.0
        )

        # Phase 4a スコア情報（複数候補時）
        candidate_scores = result.get('candidate_scores', [])
        recommendation = 'N/A'
        confidence = 'N/A'

        if candidate_scores and len(candidate_scores) > 0:
            best = candidate_scores[0]
            recommendation = best.get('recommendation', 'N/A')
            confidence = best.get('confidence', 'N/A')
        else:
            confidence = 'high' if compared_fields >= 15 else (
                'medium' if compared_fields >= 5 else 'low'
            )

        # Review reasons
        review_reasons = result.get('review_reasons', [])
        review_reason_str = ' | '.join(review_reasons)

        summary_rows.append({
            'page_number': result.get('page_no', 0),
            'pdf_date': result.get('pdf_date', ''),
            'pdf_store_name': result.get('pdf_store_name', ''),
            'mapped_store_code': result.get('store_code', ''),
            'status': result.get('status', 'unknown'),
            'match_status': match_status,
            'csv_candidate_count': csv_candidate_count,
            'compared_fields': compared_fields,
            'matched_fields': matched_fields,
            'mismatched_fields': mismatched_fields,
            'match_rate': f"{match_rate:.1%}",
            'confidence': confidence,
            'recommendation': recommendation,
            'review_reasons': review_reason_str,
        })

    df = pd.DataFrame(summary_rows)

    # CSV生成
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    csv_bytes = csv_buffer.getvalue().encode('utf-8-sig')

    filename = f"reconciliation_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    return csv_bytes, filename
