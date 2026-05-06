"""
FAX帳票・Salesforce突合確認画面（試作版）
Streamlit アプリケーション
"""

import os
import json
import base64
import csv
import io
from datetime import datetime
from pathlib import Path
import tempfile

import streamlit as st
import pandas as pd
import fitz  # PyMuPDF
from PIL import Image
from dotenv import load_dotenv

from extractor import extract_items_from_pdf, validate_extraction_result, match_with_csv

# 環境変数読込
load_dotenv()

# ページ設定
st.set_page_config(
    page_title="FAX帳票・Salesforce突合確認",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ===== CSS カスタマイズ =====
st.markdown("""
<style>
    .main {
        padding: 1rem;
    }
    .title-text {
        font-size: 28px;
        font-weight: bold;
        color: #333;
        margin-bottom: 0.2rem;
    }
    .subtitle-text {
        font-size: 14px;
        color: #666;
        margin-bottom: 1.5rem;
    }
    .info-text {
        font-size: 12px;
        color: #999;
        margin-top: 1rem;
        padding-top: 1rem;
        border-top: 1px solid #eee;
    }
    .status-match {
        background-color: #d4edda;
        color: #155724;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-weight: bold;
    }
    .status-mismatch {
        background-color: #f8d7da;
        color: #721c24;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-weight: bold;
    }
    .status-pending {
        background-color: #fff3cd;
        color: #856404;
        padding: 0.25rem 0.5rem;
        border-radius: 4px;
        font-weight: bold;
    }
    .diff-highlight {
        background-color: #ffeeee;
        border-left: 3px solid #cc0000;
        padding: 0.5rem;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ===== セッション状態の初期化 =====
if "csv_data" not in st.session_state:
    st.session_state.csv_data = None
if "pdf_files" not in st.session_state:
    st.session_state.pdf_files = []
if "extraction_results" not in st.session_state:
    st.session_state.extraction_results = []
if "matching_results" not in st.session_state:
    st.session_state.matching_results = []

# ===== メイン画面 =====
st.markdown('<div class="title-text">FAX帳票・Salesforce突合確認画面（試作版）</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle-text">帳票とSalesforce入力内容を自動照合確認します</div>', unsafe_allow_html=True)

# ===== 上部：入力エリア =====
st.markdown("### 1. ファイルをアップロード")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Salesforce CSV**")
    csv_file = st.file_uploader(
        "CSVファイルを選択",
        type=["csv"],
        key="csv_uploader",
        label_visibility="collapsed"
    )
    if csv_file is not None:
        try:
            st.session_state.csv_data = pd.read_csv(csv_file)
            st.success(f"✅ CSV読込完了：{len(st.session_state.csv_data)}件")
            with st.expander("CSVプレビュー"):
                st.dataframe(st.session_state.csv_data, use_container_width=True)
        except Exception as e:
            st.error(f"CSV読込エラー: {str(e)}")

with col2:
    st.markdown("**FAX帳票 PDF（複数可）**")
    pdf_files = st.file_uploader(
        "PDFファイルを選択",
        type=["pdf"],
        accept_multiple_files=True,
        key="pdf_uploader",
        label_visibility="collapsed"
    )
    if pdf_files:
        st.session_state.pdf_files = pdf_files
        st.success(f"✅ PDF選択完了：{len(pdf_files)}ファイル")

# ===== 実行ボタン =====
st.markdown("### 2. 照合を実行")

if st.button("照合を実行", key="execute_btn", use_container_width=True):
    if st.session_state.csv_data is None:
        st.error("❌ CSVファイルを先にアップロードしてください")
    elif not st.session_state.pdf_files:
        st.error("❌ PDFファイルを先にアップロードしてください")
    else:
        with st.spinner("帳票を解析し、照合を実行しています..."):
            st.session_state.extraction_results = []
            st.session_state.matching_results = []

            # ステップ1：各PDFから項目を抽出
            for pdf_file in st.session_state.pdf_files:
                pdf_bytes = pdf_file.read()
                try:
                    result = extract_items_from_pdf(pdf_bytes, pdf_file.name)
                    st.session_state.extraction_results.append(result)
                except Exception as e:
                    st.warning(f"⚠️ {pdf_file.name} の処理に失敗: {str(e)}")

            # ステップ2：CSVと照合
            if st.session_state.extraction_results:
                st.session_state.matching_results = match_with_csv(
                    st.session_state.extraction_results,
                    st.session_state.csv_data
                )
                st.success("✅ 照合完了")

# ===== 中央：結果一覧 =====
if st.session_state.matching_results:
    st.markdown("### 3. 照合結果")

    # 結果サマリー
    results_df = pd.DataFrame(st.session_state.matching_results)

    col1, col2, col3 = st.columns(3)
    with col1:
        match_count = len(results_df[results_df['status'] == '一致'])
        st.metric("一致", match_count)
    with col2:
        mismatch_count = len(results_df[results_df['status'] == '不一致'])
        st.metric("不一致", mismatch_count)
    with col3:
        pending_count = len(results_df[results_df['status'] == '要確認'])
        st.metric("要確認", pending_count)

    # 詳細一覧
    st.markdown("#### 詳細一覧")

    # 表示用のDataFrame を作成
    display_df = results_df[[
        'filename', 'date', 'store', 'name', 'data_no', 'tab_no',
        'extracted_count', 'csv_count', 'status'
    ]].copy()

    display_df.columns = [
        'ファイル', '日付', '店舗', '氏名', 'DataNo', 'TabNo',
        '抽出件数', 'CSV件数', 'ステータス'
    ]

    # ステータスを色分け表示
    def status_color(status):
        if status == '一致':
            return '🟢 一致'
        elif status == '不一致':
            return '🔴 不一致'
        else:
            return '🟡 要確認'

    display_df['ステータス'] = display_df['ステータス'].apply(status_color)

    st.dataframe(display_df, use_container_width=True, height=300)

    # ===== 下部：詳細表示 =====
    st.markdown("### 4. 詳細確認（差分表示）")

    selected_idx = st.selectbox(
        "詳細を確認するファイルを選択",
        range(len(st.session_state.matching_results)),
        format_func=lambda i: st.session_state.matching_results[i]['filename']
    )

    if selected_idx is not None:
        result = st.session_state.matching_results[selected_idx]

        col_left, col_right = st.columns([1, 1])

        with col_left:
            st.markdown("#### 帳票プレビュー")
            if 'pdf_preview' in result:
                st.image(result['pdf_preview'], use_container_width=True)

        with col_right:
            st.markdown("#### 抽出結果 vs CSV値")

            # 抽出値
            st.write("**抽出された項目**")
            extracted = result['extracted']
            st.json({
                '日付': extracted.get('date'),
                '店舗名': extracted.get('store'),
                '氏名': extracted.get('name'),
                '日報DataNo': extracted.get('data_no'),
                'タブレットNo': extracted.get('tab_no'),
                '件数': extracted.get('count'),
                '合計値': extracted.get('total'),
                '備考': extracted.get('notes'),
            })

            # CSV値（該当レコード）
            st.write("**CSV側の対応レコード**")
            if result.get('csv_record') is not None:
                csv_rec = result['csv_record']
                st.json({
                    '日報DataNo': csv_rec.get('data_no'),
                    'タブレットNo': csv_rec.get('tab_no'),
                    '件数': csv_rec.get('count'),
                    '合計値': csv_rec.get('total'),
                })

                # 差分表示
                st.write("**差分検出**")
                diffs = result.get('diffs', [])
                if diffs:
                    for diff in diffs:
                        st.markdown(f"""
                        <div class="diff-highlight">
                        <strong>{diff['field']}</strong><br>
                        抽出値: {diff['extracted']}<br>
                        CSV値: {diff['csv']}<br>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.success("✅ 差分なし（完全一致）")
            else:
                st.info("⚠️ CSVに対応するレコードが見つかりません")

# ===== 出力セクション =====
if st.session_state.matching_results:
    st.markdown("### 5. 結果をダウンロード")

    # 結果をCSV形式で出力
    results_df = pd.DataFrame(st.session_state.matching_results)

    output_df = results_df[[
        'filename', 'date', 'store', 'name', 'data_no', 'tab_no',
        'extracted_count', 'csv_count', 'status'
    ]].copy()

    output_df.columns = [
        'ファイル', '日付', '店舗', '氏名', 'DataNo', 'TabNo',
        '抽出件数', 'CSV件数', 'ステータス'
    ]

    csv_buffer = io.StringIO()
    output_df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
    csv_data = csv_buffer.getvalue()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    st.download_button(
        label="結果をCSVダウンロード",
        data=csv_data,
        file_name=f"matching_result_{timestamp}.csv",
        mime="text/csv"
    )

st.markdown("""
<div class="info-text">
※ 本画面は試作版です。抽出結果は原本を確認のうえ必要に応じて修正してください。
※ 正の字読取は100%正確ではありません。確認結果が「要確認」の場合は人による検証をお願いします。
</div>
""", unsafe_allow_html=True)
