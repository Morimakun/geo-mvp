"""
FAX帳票 × Salesforce CSV 照合確認画面（Phase 6A：PDF一括アップロード版）
Streamlit アプリケーション

照合ロジックは reconciliation.py に分離済み
このアプリはPDF一括アップロード→内部読み取り→照合をメイン機能として提供
"""

import io
import csv
from datetime import datetime
from pathlib import Path
import tempfile

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from reconciliation import (
    load_extraction_results,
    load_salesforce_csv,
    reconcile,
    normalize_date,
    filter_csv_by_business_date,
    ExtractionResult,
    SalesforceRecord
)
from extractor import extract_items_from_pdf

# 環境変数読込
load_dotenv()

# ページ設定
st.set_page_config(
    page_title="FAX帳票・Salesforce照合システム",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ===== CSS カスタマイズ =====
st.markdown("""
<style>
    /* メイン背景 */
    .main {
        padding: 1rem 1rem;
        background-color: #ffffff;
    }

    /* ヘッダー */
    .header-container {
        margin-bottom: 1rem;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid #e2e8f0;
    }

    .title-text {
        font-size: 32px;
        font-weight: 700;
        color: #1a202c;
        margin-bottom: 0.5rem;
        letter-spacing: -0.5px;
    }

    .subtitle-text {
        font-size: 15px;
        color: #4a5568;
        line-height: 1.6;
        margin-bottom: 0;
    }

    /* セクション */
    .section-container {
        background-color: #fafbfc;
        border-radius: 6px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: none;
        border: 1px solid #e2e8f0;
    }

    .section-title {
        font-size: 16px;
        font-weight: 600;
        color: #2d3748;
        margin-bottom: 0.75rem;
        padding-bottom: 0.5rem;
        border-bottom: 1px solid #e2e8f0;
    }

    /* カード */
    .metric-card {
        background-color: #ffffff;
        border-radius: 6px;
        padding: 1rem;
        border-left: 3px solid #2d3748;
        text-align: center;
        box-shadow: none;
        border: 1px solid #e2e8f0;
    }

    .metric-card.match {
        border-left-color: #38a169;
    }

    .metric-card.mismatch {
        border-left-color: #c53030;
    }

    .metric-card.pending {
        border-left-color: #c05621;
    }

    .metric-number {
        font-size: 28px;
        font-weight: 700;
        margin-bottom: 0.25rem;
        color: #1a202c;
    }

    .metric-label {
        font-size: 12px;
        color: #718096;
        font-weight: 500;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }

    /* 入力ボックス */
    .upload-box {
        background-color: #fafbfc;
        border: 1px solid #cbd5e0;
        border-radius: 6px;
        padding: 1rem;
        text-align: center;
        transition: all 0.3s ease;
    }

    .upload-box:hover {
        border-color: #2d3748;
        background-color: #f7fafc;
    }

    .upload-label {
        font-size: 14px;
        font-weight: 600;
        color: #2d3748;
        margin-bottom: 0.5rem;
        display: block;
    }

    .upload-description {
        font-size: 12px;
        color: #718096;
        margin-bottom: 1rem;
        line-height: 1.5;
    }

    /* ステータスバッジ */
    .status-match {
        background-color: #e6fffa;
        color: #234e52;
        padding: 0.35rem 0.75rem;
        border-radius: 4px;
        border: 1px solid #c6f6d5;
        font-weight: 600;
        font-size: 12px;
        display: inline-block;
        letter-spacing: 0.3px;
    }

    .status-mismatch {
        background-color: #fff5f5;
        color: #6b2c2c;
        padding: 0.35rem 0.75rem;
        border-radius: 4px;
        border: 1px solid #fed7d7;
        font-weight: 600;
        font-size: 12px;
        display: inline-block;
        letter-spacing: 0.3px;
    }

    .status-pending {
        background-color: #fffaf0;
        color: #7c2d12;
        padding: 0.35rem 0.75rem;
        border-radius: 4px;
        border: 1px solid #feebc8;
        font-weight: 600;
        font-size: 12px;
        display: inline-block;
        letter-spacing: 0.3px;
    }

    /* 情報ボックス */
    .info-box {
        background-color: #eff6ff;
        border-left: 4px solid #2196F3;
        padding: 1rem;
        margin: 1rem 0;
        border-radius: 4px;
        font-size: 13px;
        color: #1e40af;
        line-height: 1.5;
    }

    /* 差分ハイライト */
    .diff-highlight {
        background-color: #fff5f5;
        border-left: 4px solid #fc8181;
        padding: 1rem;
        margin: 0.5rem 0;
        border-radius: 4px;
        font-size: 13px;
        color: #742a2a;
    }

    /* データ比較セクション */
    .data-comparison {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 2rem;
        margin-top: 1.5rem;
    }

    @media (max-width: 768px) {
        .data-comparison {
            grid-template-columns: 1fr;
        }
    }

    .data-column {
        background-color: #f7fafc;
        padding: 1.5rem;
        border-radius: 6px;
        border: 1px solid #e2e8f0;
    }

    .data-column-title {
        font-size: 14px;
        font-weight: 600;
        color: #2d3748;
        margin-bottom: 1rem;
        padding-bottom: 0.75rem;
        border-bottom: 2px solid #edf2f7;
    }

    .data-item {
        margin-bottom: 0.75rem;
        font-size: 13px;
    }

    .data-label {
        color: #718096;
        font-weight: 500;
    }

    .data-value {
        color: #2d3748;
        font-weight: 600;
        word-break: break-all;
    }

    /* テーブルスタイル */
    .stDataFrame {
        font-size: 13px !important;
    }

    /* ボタンスタイル */
    .button-group {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 1rem;
        margin: 1.5rem 0;
    }

    @media (max-width: 768px) {
        .button-group {
            grid-template-columns: 1fr;
        }
    }

    /* フッター */
    .footer-text {
        text-align: center;
        color: #a0aec0;
        font-size: 12px;
        margin-top: 3rem;
        padding-top: 1.5rem;
        border-top: 1px solid #e2e8f0;
        line-height: 1.8;
    }

    /* サンプルデータ表示 */
    .sample-badge {
        display: inline-block;
        background-color: #fed7d7;
        color: #742a2a;
        padding: 0.4rem 0.8rem;
        border-radius: 4px;
        font-size: 12px;
        font-weight: 600;
        margin-bottom: 1rem;
    }
</style>
""", unsafe_allow_html=True)

# ===== セッション状態の初期化 =====
if "salesforce_csv" not in st.session_state:
    st.session_state.salesforce_csv = None
if "extraction_csv" not in st.session_state:
    st.session_state.extraction_csv = None
if "reconciliation_results" not in st.session_state:
    st.session_state.reconciliation_results = None
if "salesforce_records" not in st.session_state:
    st.session_state.salesforce_records = None
if "extraction_results" not in st.session_state:
    st.session_state.extraction_results = None
if "extraction_results_from_pdf" not in st.session_state:
    st.session_state.extraction_results_from_pdf = None
if "using_sample_data" not in st.session_state:
    st.session_state.using_sample_data = False
if "pdf_files" not in st.session_state:
    st.session_state.pdf_files = None
if "active_tab_context" not in st.session_state:
    st.session_state.active_tab_context = "pdf"  # Default to PDF tab

# Step 3: 対象営業日フィルタ用の session_state 初期化
if "target_business_date" not in st.session_state:
    st.session_state.target_business_date = None
if "csv_date_candidates" not in st.session_state:
    st.session_state.csv_date_candidates = None
if "filtered_csv_df" not in st.session_state:
    st.session_state.filtered_csv_df = None
if "filtered_salesforce_records" not in st.session_state:
    st.session_state.filtered_salesforce_records = None
if "detected_date_column" not in st.session_state:
    st.session_state.detected_date_column = None

# ===== ヘルパー関数 =====

def read_csv_with_fallback(uploaded_file):
    """
    複数のエンコーディングを試してCSVを読み込む関数

    日本語CSVを扱うため、UTF-8を優先するのではなく、
    cp932 / shift_jis を優先して試す。

    Args:
        uploaded_file: Streamlit のアップロードファイルオブジェクト

    Returns:
        (df, encoding, error_message):
        - 成功時: (DataFrame, 使用エンコーディング, None)
        - 失敗時: (None, None, エラーメッセージ)
    """
    encodings = ["utf-8-sig", "cp932", "shift_jis", "utf-8"]
    last_error = None

    for encoding in encodings:
        try:
            # ファイルポインタをリセット
            uploaded_file.seek(0)

            # CSV読込
            df = pd.read_csv(uploaded_file, encoding=encoding, on_bad_lines='skip')

            # 成功時は encoding 情報と共に返す
            return df, encoding, None
        except Exception as e:
            last_error = e
            continue

    # すべてのエンコーディングで失敗した場合
    error_message = (
        "CSVを読み込めませんでした。UTF-8 / CP932 / Shift_JIS で読み込みを試しましたが失敗しました。"
        "ファイル形式または文字コードをご確認ください。"
    )

    return None, None, error_message


def dict_to_extraction_result(data: dict, filename: str) -> ExtractionResult:
    """
    帳票読み取り結果 (Dict) → ExtractionResult に変換

    Args:
        data: extractor.py から返された辞書
        filename: アップロードされたPDFファイル名（data に filename が無い場合のフォールバック）
    """
    # エラー判定
    has_error = bool(data.get("error"))

    # Phase 6Aでは left_totals / right_totals の取得が未対応
    # 将来的に実装される予定だが、現在は空配列のため needs_review=True にして誤判定を防ぐ
    left_totals = []
    right_totals = []

    # needs_review の判定基準
    # （either left_totals OR right_totals が未取得なら needs_review=True）
    needs_review = has_error or (not left_totals or not right_totals)

    return ExtractionResult(
        file_name=data.get("filename") or filename,
        date=data.get("date"),
        page_number=data.get("page_number", 0),  # ページ番号（複数ページ対応）
        daily_report_no=data.get("data_no") or "",
        tablet_no=data.get("tab_no") or "",
        store_code=data.get("store_code") or "",
        store_name=data.get("store") or "",
        staff_name=data.get("name") or "",
        left_totals=left_totals,
        right_totals=right_totals,
        needs_review=needs_review
    )


def extract_results_from_pdfs(pdf_files: list) -> list:
    """複数の PDF から ExtractionResult リストを生成（複数ページ対応）"""
    from typing import List
    results = []
    for pdf_file in pdf_files:
        pdf_bytes = pdf_file.getvalue()
        filename = pdf_file.name

        try:
            # 帳票読み取り処理を実行（複数ページ対応）
            # extract_items_from_pdf() は List[Dict] を返すように修正
            extracted_list = extract_items_from_pdf(pdf_bytes, filename)

            # 各ページの抽出結果を ExtractionResult に変換
            for extracted_dict in extracted_list:
                result = dict_to_extraction_result(extracted_dict, filename)
                results.append(result)
        except Exception as e:
            st.warning(f"⚠️ {filename} の読み取りに失敗しました: {str(e)}")

    return results


# ===== ヘッダー =====
with st.container():
    st.markdown("""
    <div class="header-container">
        <div class="title-text">FAX帳票 × Salesforce 照合確認</div>
        <div class="subtitle-text">FAX帳票PDFの複数アップロード → 自動読み取り → Salesforce CSVとの照合を実施します</div>
    </div>
    """, unsafe_allow_html=True)

# ===== メイン処理 =====
# ===== タブ UI =====
tab1, tab2 = st.tabs(["📄 PDF一括アップロード", "📋 CSVデモモード"])

# ===== Tab 1: PDFアップロードモード =====
with tab1:
    st.session_state.active_tab_context = "pdf"

    # ===== 入力セクション =====
    with st.container():
        st.markdown('<div class="section-container">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">ファイルをアップロード</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2, gap="large")

        # Salesforce CSV アップロード
        with col1:
            st.markdown('<div class="upload-label">① Salesforce CSV</div>', unsafe_allow_html=True)
            st.markdown('<div class="upload-description">店舗日報の基準データ（日付、店舗、スタッフ、DataNo、TabNo など）</div>', unsafe_allow_html=True)

            salesforce_file_pdf = st.file_uploader(
                "Salesforce CSVを選択",
                type=["csv"],
                key="salesforce_uploader_pdf",
                label_visibility="collapsed"
            )

            if salesforce_file_pdf is not None:
                try:
                    # Step 3: 複数エンコーディング対応で最初に読込（UTF-8固定を避ける）
                    df_csv, encoding_used, error_msg = read_csv_with_fallback(salesforce_file_pdf)

                    if error_msg:
                        st.error(f"❌ {error_msg}")
                    else:
                        # 日付列を動的に検出
                        from reconciliation import find_date_column
                        date_col = find_date_column(df_csv)

                        # 成功時：エンコーディング情報と日付列名を表示
                        if date_col:
                            st.info(f"✓ CSV読込成功：{len(df_csv)}行 × {len(df_csv.columns)}列  文字コード：{encoding_used}  日付列：{date_col}")
                        else:
                            st.info(f"✓ CSV読込成功：{len(df_csv)}行 × {len(df_csv.columns)}列  文字コード：{encoding_used}")

                        # load_salesforce_csv() 用に temp CSV に保存
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                            df_csv.to_csv(tmp.name, index=False, encoding='utf-8')
                            tmp_path = tmp.name

                        st.session_state.salesforce_records = load_salesforce_csv(tmp_path)
                        st.session_state.using_sample_data = False
                        st.success(f"✓ {len(st.session_state.salesforce_records)}件のレコードを読込")

                        if date_col:
                            # 日付別の件数を集計
                            date_counts = df_csv[date_col].value_counts().sort_index()
                            st.session_state.csv_date_candidates = date_counts.to_dict()

                            # 日付候補を表示
                            st.markdown("**📅 CSV内の日付候補**")
                            cols = st.columns(len(st.session_state.csv_date_candidates))
                            for col, (date, count) in zip(cols, st.session_state.csv_date_candidates.items()):
                                with col:
                                    st.metric(f"{date}", f"{count}件")

                        # CSV全体をメモリに保持
                        st.session_state.salesforce_csv = df_csv

                        with st.expander("プレビュー"):
                            st.dataframe(df_csv.head(5), use_container_width=True)
                except Exception as e:
                    st.error(f"読込エラー: {str(e)}")

        # Step 3: 対象営業日選択セクション
        if st.session_state.salesforce_csv is not None:
            st.markdown('<div style="margin-top: 1rem; padding-top: 1rem; border-top: 1px solid #e2e8f0;"></div>', unsafe_allow_html=True)
            st.markdown('<div class="section-title">対象営業日を選択</div>', unsafe_allow_html=True)
            st.markdown('<div class="upload-description">照合対象となる営業日を選択してください。CSV内の日付列をこの日付で絞り込みます。</div>', unsafe_allow_html=True)

            target_date = st.date_input(
                "対象営業日",
                value=None,
                label_visibility="collapsed"
            )

            if target_date is not None:
                # 対象営業日を YYYY-MM-DD 形式で文字列化
                target_date_str = target_date.strftime("%Y-%m-%d")
                st.session_state.target_business_date = target_date_str

                # フィルタ実行
                if st.session_state.salesforce_csv is not None:
                    filtered_df, error_msg, detected_date_col = filter_csv_by_business_date(
                        st.session_state.salesforce_csv,
                        target_date_str,
                        date_column=None
                    )

                    if error_msg:
                        st.warning(f"⚠️ {error_msg}")
                        st.session_state.filtered_csv_df = None
                    else:
                        st.session_state.filtered_csv_df = filtered_df
                        st.session_state.detected_date_column = detected_date_col
                        st.success(f"✓ 対象営業日：{target_date_str}、対象CSV件数：{len(filtered_df)}件")

                        # フィルタ済みCSVプレビュー（優先する列だけ表示）
                        st.markdown("**📊 フィルタ済みCSVプレビュー**")

                        # 優先表示列（存在する列だけを表示）
                        priority_cols = [
                            "日付",
                            "法人・店舗(取扱コード)",
                            "委託会社名",
                            "成約総数（新規）",
                            "HT/Mz（電話+テレビ含む）成約数",
                            "MT成約数",
                            "既存ユーザー数",
                            "全体：HT/MZ（電話＋テレビ含む）成約数計",
                            "全体：MT成約数計",
                            "全体：既存サービス数計"
                        ]

                        # 存在する列をフィルタ
                        display_cols = [col for col in priority_cols if col in filtered_df.columns]
                        if len(display_cols) > 0:
                            st.dataframe(filtered_df[display_cols].head(10), use_container_width=True)
                        else:
                            st.dataframe(filtered_df.head(10), use_container_width=True)

        # FAX帳票 PDF 複数アップロード
        with col2:
            st.markdown('<div class="upload-label">② FAX帳票PDF（複数可）</div>', unsafe_allow_html=True)
            st.markdown('<div class="upload-description">FAX帳票のPDFファイル。複数ファイルを一括アップロード可能</div>', unsafe_allow_html=True)

            pdf_files = st.file_uploader(
                "FAX帳票PDFを選択",
                type=["pdf"],
                accept_multiple_files=True,
                key="pdf_uploader",
                label_visibility="collapsed"
            )

            if pdf_files:
                st.markdown(f"📄 {len(pdf_files)}個のPDFをアップロード")
                with st.expander("ファイル一覧"):
                    for pdf_file in pdf_files:
                        st.text(f"• {pdf_file.name}")

        # ===== ボタン行 =====
        st.markdown('<div style="margin-top: 1rem;"></div>', unsafe_allow_html=True)
        col_btn1, col_btn2 = st.columns(2, gap="large")

        with col_btn1:
            if st.button("照合を実行", use_container_width=True, key="pdf_reconcile_btn", type="primary"):
                if not pdf_files:
                    st.error("⚠️ FAX帳票PDFを選択してください")
                elif st.session_state.salesforce_records is None:
                    st.error("⚠️ Salesforce CSVを先に読込んでください")
                elif st.session_state.target_business_date is None:
                    st.error("⚠️ 対象営業日を選択してください")
                elif st.session_state.filtered_csv_df is None or len(st.session_state.filtered_csv_df) == 0:
                    st.error("⚠️ 対象営業日に一致するCSVデータがありません")
                else:
                    with st.spinner("🔄 帳票読み取り + 照合処理を実行中..."):
                        try:
                            # PDFから帳票読み取り結果を生成
                            extraction_results = extract_results_from_pdfs(pdf_files)

                            # Step 3: フィルタ済みCSVレコードを生成
                            # フィルタ済みDataFrameから SalesforceRecord リストを再構築
                            filtered_df = st.session_state.filtered_csv_df
                            date_col = filtered_df.columns[-1]  # 日付列は最後の列

                            # フィルタ済みレコードを生成（簡易版：最初の数項目だけサポート）
                            filtered_records = []
                            try:
                                for idx, row in filtered_df.iterrows():
                                    record = SalesforceRecord(
                                        date=str(row[date_col]) if date_col in row else None,
                                        store_name=str(row.get("法人・店舗(取扱コード)", "")) if "法人・店舗(取扱コード)" in filtered_df.columns else None,
                                        staff_name="",
                                        daily_report_no="",
                                        tablet_no="",
                                        left_total_1="",
                                        left_total_2="",
                                        left_total_3="",
                                        right_total_1="",
                                        right_total_2=""
                                    )
                                    filtered_records.append(record)
                            except:
                                # フィルタ済みレコード生成に失敗した場合は全レコードを使用
                                filtered_records = st.session_state.salesforce_records

                            # Salesforce CSVと照合
                            st.session_state.extraction_results_from_pdf = extraction_results
                            results = []
                            for extraction in extraction_results:
                                result = reconcile(extraction, filtered_records)
                                results.append(result)

                            st.session_state.reconciliation_results = results

                            # 確認理由の具体化（PDFモード用）
                            # needs_review=True かつ left_totals/right_totals が両方未取得の場合
                            for result in results:
                                if result.extraction.needs_review and not result.extraction.left_totals and not result.extraction.right_totals:
                                    # review_reasons は List[str] なので、より具体的な理由に置き換える
                                    result.review_reasons = ["帳票合計欄の読み取り未対応または未取得のため、確認が必要です"]

                            st.success(f"✓ {len(results)}件の照合が完了しました")
                        except Exception as e:
                            st.error(f"照合処理エラー: {str(e)}")

        st.markdown('</div>', unsafe_allow_html=True)

    # 照合結果がある場合は表示（PDFモード）
    if st.session_state.reconciliation_results:
        results = st.session_state.reconciliation_results

        # 統計カウント
        status_counts = {}
        for result in results:
            status = result.status
            status_counts[status] = status_counts.get(status, 0) + 1

        # ===== サマリーセクション =====
        with st.container():
            st.markdown('<div class="section-container">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">照合結果サマリー</div>', unsafe_allow_html=True)

            # Step 3: 対象営業日を表示
            if st.session_state.target_business_date:
                st.markdown(f"**対象営業日:** {st.session_state.target_business_date} | **対象CSV件数:** {len(st.session_state.filtered_csv_df)}件")

            # メトリクスカード
            col1, col2, col3, col4 = st.columns(4, gap="small")

            with col1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-number">{len(results)}</div>
                    <div class="metric-label">照合対象件数</div>
                </div>
                """, unsafe_allow_html=True)

            with col2:
                match_count = status_counts.get("一致", 0)
                match_pct = int((match_count / len(results) * 100)) if len(results) > 0 else 0
                st.markdown(f"""
                <div class="metric-card match">
                    <div class="metric-number" style="color: #22863a;">{match_count}</div>
                    <div class="metric-label">一致</div>
                    <div style="font-size: 11px; color: #666; margin-top: 0.5rem;">{match_pct}%</div>
                </div>
                """, unsafe_allow_html=True)

            with col3:
                mismatch_count = status_counts.get("不一致", 0)
                mismatch_pct = int((mismatch_count / len(results) * 100)) if len(results) > 0 else 0
                st.markdown(f"""
                <div class="metric-card mismatch">
                    <div class="metric-number" style="color: #cb2431;">{mismatch_count}</div>
                    <div class="metric-label">不一致</div>
                    <div style="font-size: 11px; color: #666; margin-top: 0.5rem;">{mismatch_pct}%</div>
                </div>
                """, unsafe_allow_html=True)

            with col4:
                pending_count = status_counts.get("要確認", 0)
                pending_pct = int((pending_count / len(results) * 100)) if len(results) > 0 else 0
                st.markdown(f"""
                <div class="metric-card pending">
                    <div class="metric-number" style="color: #bf8700;">{pending_count}</div>
                    <div class="metric-label">要確認</div>
                    <div style="font-size: 11px; color: #666; margin-top: 0.5rem;">{pending_pct}%</div>
                </div>
                """, unsafe_allow_html=True)

            # 補足指標（Phase 1: 直接キー照合未対応）
            with st.expander("補足指標"):
                # Phase 1では日報DataNo/タブレットNoがCSVに存在しないため、直接キー照合は0%
                needs_review_count = sum(1 for r in results if r.status == "要確認")
                csv_matched_count = sum(1 for r in results if r.matched_record is not None)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown("### 直接キー照合")
                    st.markdown("**未対応** (0%)")
                    st.markdown("<small>CSVに日報DataNo/タブレットNo列が存在しないため</small>", unsafe_allow_html=True)
                with col2:
                    st.markdown("### 現在の判定")
                    pct_review = int((needs_review_count / len(results) * 100)) if len(results) > 0 else 0
                    st.metric("要確認", f"{needs_review_count}/{len(results)}", f"{pct_review}%")
                with col3:
                    st.markdown("### CSV照合")
                    pct_matched = int((csv_matched_count / len(results) * 100)) if len(results) > 0 else 0
                    st.metric("CSV行検出", f"{csv_matched_count}/{len(results)}", f"{pct_matched}%")

            st.markdown('</div>', unsafe_allow_html=True)

        # ===== 注意文：日報DataNo/タブレットNo非存在 =====
        with st.container():
            st.warning(
                "⚠️ **重要な注記：**\n\n"
                "今回のCSVには日報DataNo / タブレットNo列が含まれていないため、"
                "これらはCSV照合キーではなく、PDF帳票の識別情報として扱います。"
                "現時点では、対象営業日・店舗コード・集計値をもとに確認する方式です。"
            )

        # ===== 結果一覧テーブル =====
        with st.container():
            st.markdown('<div class="section-container">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">照合結果一覧</div>', unsafe_allow_html=True)

            # Step 3: 対象営業日・CSV日付・法人・店舗(取扱コード)・委託会社名・ステータス・確認ステータス・メモを表示
            table_data = []
            for idx, result in enumerate(results):
                table_data.append({
                    "ページ": result.extraction.page_number if hasattr(result.extraction, 'page_number') else 1,
                    "対象営業日": str(st.session_state.target_business_date) if st.session_state.target_business_date else "-",
                    "CSV日付": result.matched_record.csv_date if result.matched_record else (result.extraction.date or "-"),
                    "法人・店舗(取扱コード)": result.matched_record.store_code if result.matched_record else (result.extraction.store_code or "-"),
                    "委託会社名": result.matched_record.company_name if result.matched_record else "-",
                    "ステータス": result.status,
                    "確認ステータス": result.confirmation_status,
                    "メモ": "CSVに日報DataNo/タブレットNo列なし。PDF側識別情報として保持。集計値ベース照合は先方確認後に確定。",
                })

            df = pd.DataFrame(table_data)

            # ステータスの色付け関数
            def color_status(val):
                if val == "一致":
                    return "background-color: #c6f6d5; color: #22543d; font-weight: 600; border-radius: 4px; padding: 2px 6px; text-align: center;"
                elif val == "不一致":
                    return "background-color: #fed7d7; color: #742a2a; font-weight: 600; border-radius: 4px; padding: 2px 6px; text-align: center;"
                elif val == "要確認":
                    return "background-color: #feebc8; color: #7c2d12; font-weight: 600; border-radius: 4px; padding: 2px 6px; text-align: center;"
                return ""

            styled_df = df.style.map(
                lambda val: color_status(val) if isinstance(val, str) and val in ["一致", "不一致", "要確認"] else "",
                subset=["ステータス"]
            )

            st.dataframe(styled_df, use_container_width=True, height=300)

            st.markdown('</div>', unsafe_allow_html=True)

        # ===== 詳細確認セクション =====
        with st.expander("詳細確認", expanded=False):
            st.markdown('<div style="padding: 0.5rem 0;"></div>', unsafe_allow_html=True)

            # Note: Using unique keys based on active tab context to avoid Streamlit duplicate element ID errors
            detail_selector_key = f"{st.session_state.active_tab_context}_detail_selector"

            selected_idx = st.selectbox(
                "詳細を確認する項目を選択",
                range(len(results)),
                format_func=lambda i: f"{results[i].file_name} - {results[i].status}",
                label_visibility="collapsed",
                key=detail_selector_key
            )

            if selected_idx is not None:
                result = results[selected_idx]

                # 基本情報
                col1, col2, col3 = st.columns([2, 1, 1], gap="small")
                with col1:
                    st.markdown(f"**ファイル**: {result.file_name}")
                with col2:
                    st.markdown(f"**対象営業日**: {st.session_state.target_business_date}")
                with col3:
                    status_badge = ""
                    if result.status == "一致":
                        status_badge = '<span class="status-match">✓ 一致</span>'
                    elif result.status == "不一致":
                        status_badge = '<span class="status-mismatch">✗ 不一致</span>'
                    else:
                        status_badge = '<span class="status-pending">? 要確認</span>'
                    st.markdown(f"**ステータス**: {status_badge}", unsafe_allow_html=True)

                # ===== 確認ステータス変更 UI（初期版：簡易機能）=====
                st.markdown("---")
                st.markdown("**確認ステータス**（初期版：簡易管理）")

                # session_state に確認ステータスを保存するキー
                confirmation_key = f"confirmation_{selected_idx}_{st.session_state.get('active_tab_context', 'default')}"

                # 初回アクセス時に初期値を設定
                if confirmation_key not in st.session_state:
                    st.session_state[confirmation_key] = result.confirmation_status

                # selectbox で確認ステータスを選択
                new_confirmation_status = st.selectbox(
                    "確認状況を選択",
                    ["未確認", "確認済み", "修正候補", "再照合済み", "要再確認"],
                    index=["未確認", "確認済み", "修正候補", "再照合済み", "要再確認"].index(st.session_state[confirmation_key]),
                    label_visibility="collapsed",
                    key=f"confirmation_select_{selected_idx}_{st.session_state.get('active_tab_context', 'default')}"
                )

                # 変更を results に反映
                if new_confirmation_status != result.confirmation_status:
                    result.confirmation_status = new_confirmation_status
                    st.session_state[confirmation_key] = new_confirmation_status
                    st.info(f"✓ 確認ステータスを「{new_confirmation_status}」に更新しました")

                st.markdown("---")

                # データ比較
                st.markdown('<div class="data-comparison">', unsafe_allow_html=True)

                # 左：帳票読み取り結果
                st.markdown("""
                <div class="data-column">
                    <div class="data-column-title">帳票読み取り結果</div>
                """, unsafe_allow_html=True)

                data_items = [
                    ("日付", result.extraction.date or "-"),
                    ("法人・店舗(取扱コード)", result.extraction.store_code or "-"),
                    ("担当者", result.extraction.staff_name or "-"),
                    ("DataNo", result.extraction.daily_report_no or "-"),
                    ("TabNo", result.extraction.tablet_no or "-"),
                    ("左下合計", "/".join(result.extraction.left_totals) if result.extraction.left_totals else "-"),
                    ("右下合計", "/".join(result.extraction.right_totals) if result.extraction.right_totals else "-"),
                ]

                for label, value in data_items:
                    st.markdown(f"""
                    <div class="data-item">
                        <span class="data-label">{label}</span>: <span class="data-value">{value}</span>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

                # 右：Salesforceレコード
                st.markdown("""
                <div class="data-column">
                    <div class="data-column-title">Salesforceレコード</div>
                """, unsafe_allow_html=True)

                if result.matched_record:
                    csv_data_items = [
                        ("日付", result.matched_record.csv_date or "-"),
                        ("店舗", result.matched_record.company_name or "-"),
                        ("担当者", result.matched_record.staff_name),
                        ("DataNo", result.matched_record.daily_report_no),
                        ("TabNo", result.matched_record.tablet_no),
                        ("左下合計", "-"),
                        ("右下合計", "-"),
                    ]

                    for label, value in csv_data_items:
                        st.markdown(f"""
                        <div class="data-item">
                            <span class="data-label">{label}</span>: <span class="data-value">{value}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color: #c53030; font-weight: 600;">対応するレコードが見つかりません</p>', unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("---")

                # 差分と確認理由
                col1, col2 = st.columns(2, gap="large")

                with col1:
                    if result.differences:
                        st.markdown("#### 差分内容")
                        for diff in result.differences:
                            st.markdown(f'<div class="diff-highlight">{diff}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown("#### 差分内容")
                        st.markdown('<p style="color: #718096;">差分がありません</p>', unsafe_allow_html=True)

                with col2:
                    if result.review_reasons:
                        st.markdown("#### 確認理由")
                        for reason in result.review_reasons:
                            st.info(reason)
                    else:
                        st.markdown("#### 確認理由")
                        st.markdown('<p style="color: #718096;">確認不要</p>', unsafe_allow_html=True)

        # ===== ダウンロード =====
        with st.container():
            st.markdown('<div style="margin-top: 0.75rem; margin-bottom: 1rem;"></div>', unsafe_allow_html=True)

            # CSV形式で出力
            csv_rows = [
                [
                    "ファイル",
                    "マッチング方式",
                    "帳票_日付",
                    "帳票_店舗",
                    "帳票_スタッフ",
                    "帳票_DataNo",
                    "帳票_TabNo",
                    "帳票_左下合計",
                    "帳票_右下合計",
                    "CSV_日付",
                    "CSV_店舗",
                    "CSV_スタッフ",
                    "CSV_DataNo",
                    "CSV_TabNo",
                    "CSV_左下合計",
                    "CSV_右下合計",
                    "ステータス",
                    "差分内容",
                    "確認理由"
                ]
            ]

            for result in results:
                csv_rows.append([
                    result.file_name,
                    "",  # マッチング方式（Phase 1では未使用）
                    result.extraction.date or "",
                    result.extraction.store_code or "",
                    result.extraction.staff_name or "",
                    result.extraction.daily_report_no or "",
                    result.extraction.tablet_no or "",
                    "/".join(result.extraction.left_totals) if result.extraction.left_totals else "",
                    "/".join(result.extraction.right_totals) if result.extraction.right_totals else "",
                    result.matched_record.csv_date or "-" if result.matched_record else "",
                    result.matched_record.company_name or "-" if result.matched_record else "",
                    result.matched_record.staff_name if result.matched_record else "",
                    result.matched_record.daily_report_no if result.matched_record else "",
                    result.matched_record.tablet_no if result.matched_record else "",
                    "-" if result.matched_record else "",
                    "-" if result.matched_record else "",
                    result.status,
                    " | ".join(result.differences) if result.differences else "",
                    " | ".join(result.review_reasons) if result.review_reasons else ""
                ])

            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            for row in csv_rows:
                writer.writerow(row)
            csv_data = csv_buffer.getvalue()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            st.download_button(
                label="結果をCSVダウンロード",
                data=csv_data,
                file_name=f"reconciliation_result_{timestamp}.csv",
                mime="text/csv",
                use_container_width=True
            )

        # ===== 修正後CSV再取り込み / 再照合セクション =====
        st.markdown('<div class="section-container">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">修正後CSVの再取り込み / 再照合</div>', unsafe_allow_html=True)
        st.markdown('<div class="upload-description">Salesforce側で修正した内容を反映させるため、修正後のCSVを再度アップロードして再照合できます。</div>', unsafe_allow_html=True)

        # 初回結果を保存（初めて照合を実行した時点）
        if "initial_reconciliation_results" not in st.session_state or st.session_state.initial_reconciliation_results is None:
            st.session_state.initial_reconciliation_results = results

        col_revised1, col_revised2 = st.columns(2, gap="large")

        with col_revised1:
            st.markdown('<div class="upload-label">修正後のSalesforce CSV</div>', unsafe_allow_html=True)
            st.markdown('<div class="upload-description">Salesforce側で修正したCSVをアップロード</div>', unsafe_allow_html=True)

            revised_csv_file = st.file_uploader(
                "修正後CSVを選択",
                type=["csv"],
                key="revised_csv_uploader_pdf",
                label_visibility="collapsed"
            )

        with col_revised2:
            st.markdown('<div class="upload-label">再照合実行</div>', unsafe_allow_html=True)

            if revised_csv_file is not None and st.button("修正後CSVで再照合を実行", type="primary", use_container_width=True, key="rereconcile_btn"):
                try:
                    # 修正後CSVを読み込み
                    revised_df, encoding_used, error_msg = read_csv_with_fallback(revised_csv_file)

                    if error_msg:
                        st.error(f"❌ {error_msg}")
                    else:
                        st.info(f"✓ 修正後CSV読込成功：{len(revised_df)}行")

                        # 修正後CSVから SalesforceRecord を生成
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                            revised_df.to_csv(tmp.name, index=False, encoding='utf-8')
                            tmp_path = tmp.name

                        revised_records = load_salesforce_csv(tmp_path)

                        # 同じPDF結果で再照合
                        rereconciled_results = []
                        if st.session_state.extraction_results_from_pdf:
                            for extraction in st.session_state.extraction_results_from_pdf:
                                result = reconcile(extraction, revised_records)
                                rereconciled_results.append(result)

                        st.session_state.rereconciliation_results = rereconciled_results
                        st.success(f"✓ {len(rereconciled_results)}件の再照合が完了しました")

                        # 初回結果との比較（キーベース照合）
                        st.markdown("**再照合結果の比較（キーベース照合）**")

                        # キーベース照合用の辞書を作成
                        from reconciliation import generate_comparison_key

                        rereconciled_by_key = {}
                        for result in rereconciled_results:
                            key = generate_comparison_key(result)
                            if key:
                                rereconciled_by_key[key] = result

                        comparison_data = []
                        resolved_count = 0
                        still_mismatch_count = 0
                        still_pending_count = 0
                        newly_mismatch_count = 0

                        for initial in st.session_state.initial_reconciliation_results:
                            initial_key = generate_comparison_key(initial)

                            # 再照合結果をキーで検索
                            rereconciled = None
                            if initial_key:
                                rereconciled = rereconciled_by_key.get(initial_key)

                            if not rereconciled:
                                # 比較キー不足の場合
                                status_change = "⚠️ 比較キー不足"
                                row_data = {
                                    "ファイル": initial.file_name,
                                    "初回判定": initial.status,
                                    "再照合判定": "（比較できず）",
                                    "照合キー": initial_key or "なし",
                                    "変化": status_change
                                }
                            else:
                                # キーベースで比較結果を分類
                                if initial.status == "不一致" and rereconciled.status in ["一致", "要確認"]:
                                    status_change = "✓ 解消"
                                    resolved_count += 1
                                elif initial.status == "不一致" and rereconciled.status == "不一致":
                                    status_change = "⚠️ まだ不一致"
                                    still_mismatch_count += 1
                                elif initial.status == "要確認" and rereconciled.status == "要確認":
                                    status_change = "? 要確認のまま"
                                    still_pending_count += 1
                                elif initial.status in ["一致", "要確認"] and rereconciled.status == "不一致":
                                    status_change = "❌ 新たに不一致"
                                    newly_mismatch_count += 1
                                else:
                                    status_change = "→ " + rereconciled.status

                                row_data = {
                                    "ファイル": initial.file_name,
                                    "初回判定": initial.status,
                                    "再照合判定": rereconciled.status,
                                    "照合キー": initial_key or "なし",
                                    "変化": status_change
                                }

                            comparison_data.append(row_data)

                        df_comparison = pd.DataFrame(comparison_data)
                        st.dataframe(df_comparison, use_container_width=True, height=250)

                        # 統計表示
                        col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4, gap="small")
                        with col_stat1:
                            st.metric("解消済み", f"{resolved_count}件")
                        with col_stat2:
                            st.metric("まだ不一致", f"{still_mismatch_count}件")
                        with col_stat3:
                            st.metric("要確認のまま", f"{still_pending_count}件")
                        with col_stat4:
                            st.metric("新たに不一致", f"{newly_mismatch_count}件")

                except Exception as e:
                    st.error(f"再照合処理エラー: {str(e)}")

        st.markdown('</div>', unsafe_allow_html=True)


# ===== Tab 2: CSVデモモード =====
with tab2:
    st.session_state.active_tab_context = "csv"

    # ===== 入力セクション =====
    with st.container():
        st.markdown('<div class="section-container">', unsafe_allow_html=True)
        st.markdown('<div class="section-title">CSVファイルをアップロード</div>', unsafe_allow_html=True)

        col1, col2 = st.columns(2, gap="large")

        # Salesforce CSV アップロード
        with col1:
            st.markdown('<div class="upload-label">① Salesforce CSV</div>', unsafe_allow_html=True)
            st.markdown('<div class="upload-description">店舗日報の基準データ（日付、店舗、スタッフ、DataNo、TabNo など）</div>', unsafe_allow_html=True)

            salesforce_file = st.file_uploader(
                "Salesforce CSVを選択",
                type=["csv"],
                key="salesforce_uploader",
                label_visibility="collapsed"
            )

            if salesforce_file is not None:
                try:
                    # 複数エンコーディング対応で読込
                    df, encoding_used, error_msg = read_csv_with_fallback(salesforce_file)

                    if error_msg:
                        st.error(f"❌ {error_msg}")
                    else:
                        # 成功時：エンコーディング情報を表示
                        st.info(f"✓ CSV読込成功：{len(df)}行 × {len(df.columns)}列  文字コード：{encoding_used}")

                        # DataFrame を一度 CSV 保存して load_salesforce_csv() で読込（互換性維持）
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                            df.to_csv(tmp.name, index=False, encoding='utf-8')
                            tmp_path = tmp.name

                        st.session_state.salesforce_records = load_salesforce_csv(tmp_path)
                        st.session_state.using_sample_data = False
                        st.success(f"✓ {len(st.session_state.salesforce_records)}件のレコードを読込")

                        with st.expander("プレビュー"):
                            st.dataframe(df.head(5), use_container_width=True)
                except Exception as e:
                    st.error(f"読込エラー: {str(e)}")

        # 帳票読み取り結果CSV アップロード
        with col2:
            st.markdown('<div class="upload-label">② 帳票読み取り結果CSV</div>', unsafe_allow_html=True)
            st.markdown('<div class="upload-description">帳票から読み取ったFAX帳票の項目（日付、店舗、スタッフ、データなど）</div>', unsafe_allow_html=True)

            extraction_file = st.file_uploader(
                "帳票読み取り結果CSVを選択",
                type=["csv"],
                key="extraction_uploader",
                label_visibility="collapsed"
            )

            if extraction_file is not None:
                try:
                    # 複数エンコーディング対応で読込
                    df, encoding_used, error_msg = read_csv_with_fallback(extraction_file)

                    if error_msg:
                        st.error(f"❌ {error_msg}")
                    else:
                        # 成功時：エンコーディング情報を表示
                        st.info(f"✓ CSV読込成功：{len(df)}行 × {len(df.columns)}列  文字コード：{encoding_used}")

                        # DataFrame を一度 CSV 保存して load_extraction_results() で読込（互換性維持）
                        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                            df.to_csv(tmp.name, index=False, encoding='utf-8')
                            tmp_path = tmp.name

                        st.session_state.extraction_results = load_extraction_results(tmp_path)
                        st.session_state.using_sample_data = False
                        st.success(f"✓ {len(st.session_state.extraction_results)}件の抽出結果を読込")

                        with st.expander("プレビュー"):
                            st.dataframe(df.head(5), use_container_width=True)
                except Exception as e:
                    st.error(f"読込エラー: {str(e)}")

        # ===== ボタン行 =====
        st.markdown('<div style="margin-top: 1rem;"></div>', unsafe_allow_html=True)
        col_btn1, col_btn2 = st.columns(2, gap="large")

        with col_btn1:
            if st.button("サンプルデータで試す", use_container_width=True, key="sample_btn"):
                try:
                    script_dir = Path(__file__).parent
                    samples_dir = script_dir / "samples" / "synthetic"
                    outputs_dir = script_dir / "outputs"

                    st.session_state.salesforce_records = load_salesforce_csv(
                        str(samples_dir / "salesforce_sample.csv")
                    )
                    st.session_state.extraction_results = load_extraction_results(
                        str(outputs_dir / "synthetic_extraction_results.csv")
                    )
                    st.session_state.using_sample_data = True
                    st.session_state.reconciliation_results = None

                    st.success("✓ サンプルデータを読込完了")
                    st.info(f"Salesforce: {len(st.session_state.salesforce_records)}件 | 帳票読み取り結果: {len(st.session_state.extraction_results)}件")
                except Exception as e:
                    st.error(f"読込エラー: {str(e)}")

        with col_btn2:
            if st.button("照合を実行", use_container_width=True, key="reconcile_btn", type="primary"):
                if st.session_state.salesforce_records is None:
                    st.error("⚠️ Salesforce CSVを先に読込んでください")
                elif st.session_state.extraction_results is None:
                    st.error("⚠️ 帳票読み取り結果CSVを先に読込んでください")
                else:
                    with st.spinner("🔄 照合処理を実行中..."):
                        try:
                            results = []
                            for extraction in st.session_state.extraction_results:
                                result = reconcile(extraction, st.session_state.salesforce_records)
                                results.append(result)

                            st.session_state.reconciliation_results = results
                            st.success(f"✓ {len(results)}件の照合が完了しました")
                        except Exception as e:
                            st.error(f"照合処理エラー: {str(e)}")

        # サンプルデータ使用中の表示
        if st.session_state.using_sample_data:
            st.markdown('<div class="sample-badge">サンプルデータを使用しています</div>', unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)

    # ===== 照合結果表示（Tab 2用）=====
    if st.session_state.reconciliation_results:
        results = st.session_state.reconciliation_results

        # 統計カウント
        status_counts = {}
        for result in results:
            status = result.status
            status_counts[status] = status_counts.get(status, 0) + 1

        # ===== サマリーセクション =====
        with st.container():
            st.markdown('<div class="section-container">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">照合結果サマリー</div>', unsafe_allow_html=True)

            # メトリクスカード
            col1, col2, col3, col4 = st.columns(4, gap="small")

            with col1:
                st.markdown(f"""
                <div class="metric-card">
                    <div class="metric-number">{len(results)}</div>
                    <div class="metric-label">照合対象件数</div>
                </div>
                """, unsafe_allow_html=True)

            with col2:
                match_count = status_counts.get("一致", 0)
                match_pct = int((match_count / len(results) * 100)) if len(results) > 0 else 0
                st.markdown(f"""
                <div class="metric-card match">
                    <div class="metric-number" style="color: #22863a;">{match_count}</div>
                    <div class="metric-label">一致</div>
                    <div style="font-size: 11px; color: #666; margin-top: 0.5rem;">{match_pct}%</div>
                </div>
                """, unsafe_allow_html=True)

            with col3:
                mismatch_count = status_counts.get("不一致", 0)
                mismatch_pct = int((mismatch_count / len(results) * 100)) if len(results) > 0 else 0
                st.markdown(f"""
                <div class="metric-card mismatch">
                    <div class="metric-number" style="color: #cb2431;">{mismatch_count}</div>
                    <div class="metric-label">不一致</div>
                    <div style="font-size: 11px; color: #666; margin-top: 0.5rem;">{mismatch_pct}%</div>
                </div>
                """, unsafe_allow_html=True)

            with col4:
                pending_count = status_counts.get("要確認", 0)
                pending_pct = int((pending_count / len(results) * 100)) if len(results) > 0 else 0
                st.markdown(f"""
                <div class="metric-card pending">
                    <div class="metric-number" style="color: #bf8700;">{pending_count}</div>
                    <div class="metric-label">要確認</div>
                    <div style="font-size: 11px; color: #666; margin-top: 0.5rem;">{pending_pct}%</div>
                </div>
                """, unsafe_allow_html=True)

            # 補足指標（Phase 1: 直接キー照合未対応）
            with st.expander("補足指標"):
                # Phase 1では日報DataNo/タブレットNoがCSVに存在しないため、直接キー照合は0%
                needs_review_count = sum(1 for r in results if r.status == "要確認")
                csv_matched_count = sum(1 for r in results if r.matched_record is not None)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown("### 直接キー照合")
                    st.markdown("**未対応** (0%)")
                    st.markdown("<small>CSVに日報DataNo/タブレットNo列が存在しないため</small>", unsafe_allow_html=True)
                with col2:
                    st.markdown("### 現在の判定")
                    pct_review = int((needs_review_count / len(results) * 100)) if len(results) > 0 else 0
                    st.metric("要確認", f"{needs_review_count}/{len(results)}", f"{pct_review}%")
                with col3:
                    st.markdown("### CSV照合")
                    pct_matched = int((csv_matched_count / len(results) * 100)) if len(results) > 0 else 0
                    st.metric("CSV行検出", f"{csv_matched_count}/{len(results)}", f"{pct_matched}%")

            st.markdown('</div>', unsafe_allow_html=True)

        # ===== 結果一覧テーブル =====
        with st.container():
            st.markdown('<div class="section-container">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">照合結果一覧</div>', unsafe_allow_html=True)

            table_data = []
            for result in results:
                table_data.append({
                    "ファイル名": result.file_name,
                    "対象営業日": str(st.session_state.target_business_date) if st.session_state.target_business_date else "-",
                    "日付": result.extraction.date or "-",
                    "法人・店舗(取扱コード)": result.extraction.store_code or "-",
                    "担当者": result.extraction.staff_name or "-",
                    "ステータス": result.status,
                    "メモ": getattr(result, "memo", "") or "CSVに日報DataNo/タブレットNo列なし。PDF側識別情報として保持。",
                })

            df = pd.DataFrame(table_data)

            # ステータスの色付け関数
            def color_status(val):
                if val == "一致":
                    return "background-color: #c6f6d5; color: #22543d; font-weight: 600; border-radius: 4px; padding: 2px 6px; text-align: center;"
                elif val == "不一致":
                    return "background-color: #fed7d7; color: #742a2a; font-weight: 600; border-radius: 4px; padding: 2px 6px; text-align: center;"
                elif val == "要確認":
                    return "background-color: #feebc8; color: #7c2d12; font-weight: 600; border-radius: 4px; padding: 2px 6px; text-align: center;"
                return ""

            styled_df = df.style.map(
                lambda val: color_status(val) if isinstance(val, str) and val in ["一致", "不一致", "要確認"] else "",
                subset=["ステータス"]
            )

            st.dataframe(styled_df, use_container_width=True, height=300)

            st.markdown('</div>', unsafe_allow_html=True)

        # ===== 詳細確認セクション =====
        with st.expander("詳細確認", expanded=False):
            st.markdown('<div style="padding: 0.5rem 0;"></div>', unsafe_allow_html=True)

            # Note: Using unique keys based on active tab context to avoid Streamlit duplicate element ID errors
            detail_selector_key = f"{st.session_state.active_tab_context}_detail_selector"

            selected_idx = st.selectbox(
                "詳細を確認する項目を選択",
                range(len(results)),
                format_func=lambda i: f"{results[i].file_name} - {results[i].status}",
                label_visibility="collapsed",
                key=detail_selector_key
            )

            if selected_idx is not None:
                result = results[selected_idx]

                # 基本情報
                col1, col2, col3 = st.columns([2, 1, 1], gap="small")
                with col1:
                    st.markdown(f"**ファイル**: {result.file_name}")
                with col2:
                    st.markdown(f"**対象営業日**: {st.session_state.target_business_date}")
                with col3:
                    status_badge = ""
                    if result.status == "一致":
                        status_badge = '<span class="status-match">✓ 一致</span>'
                    elif result.status == "不一致":
                        status_badge = '<span class="status-mismatch">✗ 不一致</span>'
                    else:
                        status_badge = '<span class="status-pending">? 要確認</span>'
                    st.markdown(f"**ステータス**: {status_badge}", unsafe_allow_html=True)

                # ===== 確認ステータス変更 UI（初期版：簡易機能）=====
                st.markdown("---")
                st.markdown("**確認ステータス**（初期版：簡易管理）")

                # session_state に確認ステータスを保存するキー
                confirmation_key = f"confirmation_{selected_idx}_{st.session_state.get('active_tab_context', 'default')}"

                # 初回アクセス時に初期値を設定
                if confirmation_key not in st.session_state:
                    st.session_state[confirmation_key] = result.confirmation_status

                # selectbox で確認ステータスを選択
                new_confirmation_status = st.selectbox(
                    "確認状況を選択",
                    ["未確認", "確認済み", "修正候補", "再照合済み", "要再確認"],
                    index=["未確認", "確認済み", "修正候補", "再照合済み", "要再確認"].index(st.session_state[confirmation_key]),
                    label_visibility="collapsed",
                    key=f"confirmation_select_{selected_idx}_{st.session_state.get('active_tab_context', 'default')}"
                )

                # 変更を results に反映
                if new_confirmation_status != result.confirmation_status:
                    result.confirmation_status = new_confirmation_status
                    st.session_state[confirmation_key] = new_confirmation_status
                    st.info(f"✓ 確認ステータスを「{new_confirmation_status}」に更新しました")

                st.markdown("---")

                # データ比較
                st.markdown('<div class="data-comparison">', unsafe_allow_html=True)

                # 左：帳票読み取り結果
                st.markdown("""
                <div class="data-column">
                    <div class="data-column-title">帳票読み取り結果</div>
                """, unsafe_allow_html=True)

                data_items = [
                    ("日付", result.extraction.date or "-"),
                    ("法人・店舗(取扱コード)", result.extraction.store_code or "-"),
                    ("担当者", result.extraction.staff_name or "-"),
                    ("DataNo", result.extraction.daily_report_no or "-"),
                    ("TabNo", result.extraction.tablet_no or "-"),
                    ("左下合計", "/".join(result.extraction.left_totals) if result.extraction.left_totals else "-"),
                    ("右下合計", "/".join(result.extraction.right_totals) if result.extraction.right_totals else "-"),
                ]

                for label, value in data_items:
                    st.markdown(f"""
                    <div class="data-item">
                        <span class="data-label">{label}</span>: <span class="data-value">{value}</span>
                    </div>
                    """, unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

                # 右：Salesforceレコード
                st.markdown("""
                <div class="data-column">
                    <div class="data-column-title">Salesforceレコード</div>
                """, unsafe_allow_html=True)

                if result.matched_record:
                    csv_data_items = [
                        ("日付", result.matched_record.csv_date or "-"),
                        ("店舗", result.matched_record.company_name or "-"),
                        ("担当者", result.matched_record.staff_name),
                        ("DataNo", result.matched_record.daily_report_no),
                        ("TabNo", result.matched_record.tablet_no),
                        ("左下合計", "-"),
                        ("右下合計", "-"),
                    ]

                    for label, value in csv_data_items:
                        st.markdown(f"""
                        <div class="data-item">
                            <span class="data-label">{label}</span>: <span class="data-value">{value}</span>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.markdown('<p style="color: #c53030; font-weight: 600;">対応するレコードが見つかりません</p>', unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("---")

                # 差分と確認理由
                col1, col2 = st.columns(2, gap="large")

                with col1:
                    if result.differences:
                        st.markdown("#### 差分内容")
                        for diff in result.differences:
                            st.markdown(f'<div class="diff-highlight">{diff}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown("#### 差分内容")
                        st.markdown('<p style="color: #718096;">差分がありません</p>', unsafe_allow_html=True)

                with col2:
                    if result.review_reasons:
                        st.markdown("#### 確認理由")
                        for reason in result.review_reasons:
                            st.info(reason)
                    else:
                        st.markdown("#### 確認理由")
                        st.markdown('<p style="color: #718096;">確認不要</p>', unsafe_allow_html=True)

        # ===== ダウンロード =====
        with st.container():
            st.markdown('<div style="margin-top: 0.75rem; margin-bottom: 1rem;"></div>', unsafe_allow_html=True)

            # CSV形式で出力
            csv_rows = [
                [
                    "ファイル",
                    "マッチング方式",
                    "帳票_日付",
                    "帳票_店舗",
                    "帳票_スタッフ",
                    "帳票_DataNo",
                    "帳票_TabNo",
                    "帳票_左下合計",
                    "帳票_右下合計",
                    "CSV_日付",
                    "CSV_店舗",
                    "CSV_スタッフ",
                    "CSV_DataNo",
                    "CSV_TabNo",
                    "CSV_左下合計",
                    "CSV_右下合計",
                    "ステータス",
                    "差分内容",
                    "確認理由"
                ]
            ]

            for result in results:
                csv_rows.append([
                    result.file_name,
                    "",  # マッチング方式（Phase 1では未使用）
                    result.extraction.date or "",
                    result.extraction.store_code or "",
                    result.extraction.staff_name or "",
                    result.extraction.daily_report_no or "",
                    result.extraction.tablet_no or "",
                    "/".join(result.extraction.left_totals) if result.extraction.left_totals else "",
                    "/".join(result.extraction.right_totals) if result.extraction.right_totals else "",
                    result.matched_record.csv_date or "-" if result.matched_record else "",
                    result.matched_record.company_name or "-" if result.matched_record else "",
                    result.matched_record.staff_name if result.matched_record else "",
                    result.matched_record.daily_report_no if result.matched_record else "",
                    result.matched_record.tablet_no if result.matched_record else "",
                    "-" if result.matched_record else "",
                    "-" if result.matched_record else "",
                    result.status,
                    " | ".join(result.differences) if result.differences else "",
                    " | ".join(result.review_reasons) if result.review_reasons else ""
                ])

            csv_buffer = io.StringIO()
            writer = csv.writer(csv_buffer)
            for row in csv_rows:
                writer.writerow(row)
            csv_data = csv_buffer.getvalue()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            st.download_button(
                label="結果をCSVダウンロード",
                data=csv_data,
                file_name=f"reconciliation_result_{timestamp}.csv",
                mime="text/csv",
                use_container_width=True
            )

# ===== フッター =====
st.markdown("""
<div style="background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; padding: 0.75rem; margin-top: 2rem;">
<small>
⚠️ <b>この画面は試作版です。</b><br>
実際の読み取り精度は、実FAX帳票PDFと実Salesforce CSVでの検証後に調整します。
</small>
</div>
""", unsafe_allow_html=True)
