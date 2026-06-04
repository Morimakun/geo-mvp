"""
Phase 1 照合UI ヘルパーモジュール

app.py から呼び出される
"""

import pandas as pd
import streamlit as st
from typing import List, Dict, Optional
import io
import csv


def display_phase1_reconciliation_summary(results: List[Dict]):
    """Phase 1 照合結果サマリーを表示"""

    if not results:
        st.warning("照合結果がありません")
        return

    # ステータスカウント
    match_count = sum(1 for r in results if r['status'] == 'match')
    mismatch_count = sum(1 for r in results if r['status'] == 'mismatch')
    review_count = sum(1 for r in results if r['status'] == 'review')

    # サマリー表示
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("照合対象件数", len(results))

    with col2:
        st.metric("一致", match_count)

    with col3:
        st.metric("不一致", mismatch_count)

    with col4:
        st.metric("要確認", review_count)


def display_phase1_reconciliation_detail(results: List[Dict]):
    """Phase 1 照合詳細を表示"""

    if not results:
        return

    for idx, result in enumerate(results):
        st.markdown(f"### ページ {result.get('page_no', idx+1)}: {result['store_name']}")

        # ステータスと基本情報
        col1, col2, col3 = st.columns(3)

        with col1:
            status = result['status']
            if status == 'match':
                st.success(f"✓ 一致")
            elif status == 'mismatch':
                st.error(f"✗ 不一致")
            else:
                st.warning(f"? 要確認")

        with col2:
            st.metric("スコア", f"{result['score']:.1f}")

        with col3:
            st.metric("候補行", result.get('csv_record_idx', 'N/A'))

        # 店舗・スタッフ情報
        st.markdown("**照合情報**")
        col1, col2 = st.columns(2)

        with col1:
            st.write(f"店舗: {result['store_code']} / {result['store_name']}")
            st.write(f"一致: {result['match_count']} / 不一致: {result['diff_count']} / 読取不可: {result['unreadable_count']}")

        with col2:
            st.write(f"担当者名: {result.get('staff_name') or 'N/A'}")
            st.write(f"タブレットNo【補助】: {result.get('tablet_no') or 'N/A'}")
            st.write(f"日報No【参考】: {result.get('data_no') or 'N/A'}")

        # 詳細項目（要約）
        st.markdown("**詳細**")

        if result['matched_items']:
            matched_display = ', '.join(result['matched_items'][:5])
            if len(result['matched_items']) > 5:
                matched_display += f", ... 他{len(result['matched_items']) - 5}件"
            st.write(f"一致項目: {matched_display}")

        if result['diff_items']:
            diff_display = ', '.join(result['diff_items'][:10])
            if len(result['diff_items']) > 10:
                diff_display += f", ... 他{len(result['diff_items']) - 10}件"
            st.write(f"不一致項目: {diff_display}")

        if result['unreadable_items']:
            unreadable_display = ', '.join(result['unreadable_items'][:10])
            if len(result['unreadable_items']) > 10:
                unreadable_display += f", ... 他{len(result['unreadable_items']) - 10}件"
            st.write(f"読取不可項目: {unreadable_display}")

        # 要確認理由
        if result['review_reasons']:
            st.warning(f"要確認理由: {', '.join(result['review_reasons'])}")

        st.divider()


def create_phase1_detail_csv(results: List[Dict]) -> str:
    """Phase 1 照合詳細CSVを生成"""

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        'pdf_file',
        'page_no',
        'status',
        'score',
        'store_name_pdf',
        'store_code_candidate',
        'csv_candidate_count',
        'best_csv_row_index',
        'match_count',
        'diff_count',
        'unreadable_count',
        'review_reasons',
        'matched_items',
        'diff_items',
        'unreadable_items',
        'data_no_reference',
        'tablet_no_pdf_helper',
        'staff_name_helper'
    ])

    writer.writeheader()

    for result in results:
        writer.writerow({
            'pdf_file': '',  # app.py側で設定
            'page_no': result.get('page_no', ''),
            'status': result['status'],
            'score': f"{result['score']:.1f}",
            'store_name_pdf': result['store_name'],
            'store_code_candidate': result['store_code'],
            'csv_candidate_count': len(result.get('candidates', [])),
            'best_csv_row_index': result.get('csv_record_idx', ''),
            'match_count': result['match_count'],
            'diff_count': result['diff_count'],
            'unreadable_count': result['unreadable_count'],
            'review_reasons': ' | '.join(result['review_reasons']),
            'matched_items': ' | '.join(result['matched_items']),
            'diff_items': ' | '.join(result['diff_items']),
            'unreadable_items': ' | '.join(result['unreadable_items']),
            'data_no_reference': result.get('data_no', ''),
            'tablet_no_pdf_helper': result.get('tablet_no', ''),
            'staff_name_helper': result.get('staff_name', '')
        })

    return output.getvalue()
