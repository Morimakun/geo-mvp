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
from reconciliation_phase1 import create_phase1_engine

# 環境変数読込
load_dotenv()

# ===== ヘルパー関数：確認ログ関連 =====

import uuid
import random
import string

def generate_session_id():
    """セッションIDを生成"""
    now = datetime.now()
    date_time = now.strftime("%Y%m%d_%H%M%S")
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"{date_time}_{random_suffix}"

def build_confirmation_log_row(
    page, v3_value, v22_value, csv_value, confidence, classification,
    auto_confirm, review_required, review_reason,
    user_action, user_decision, manual_correction_value=None,
    decision_reason="", before_status="", after_status="",
    operator_name="", store_name="", store_code=""
):
    """確認ログ行を構築（27項目）"""

    log_id = f"LOG_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{page}_{user_action}"
    timestamp = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+09:00")
    session_id = st.session_state.get("confirmation_session_id", "")

    return {
        "log_id": log_id,
        "timestamp": timestamp,
        "user_id": "local_user",
        "operator_name": operator_name,
        "session_id": session_id,
        "page": page,
        "store_name": store_name,
        "store_code": store_code,
        "field_code": "AI",
        "field_name": "AI合計",
        "v3_value": str(v3_value) if v3_value is not None else "",
        "v22_value": str(v22_value) if v22_value is not None else "",
        "csv_value": str(csv_value) if csv_value is not None else "",
        "final_value": str(manual_correction_value) if manual_correction_value is not None else "",
        "confidence": confidence if confidence else "",
        "classification": classification if classification else "",
        "auto_confirm_candidate": str(auto_confirm).lower() if auto_confirm is not None else "",
        "review_required": str(review_required).lower() if review_required is not None else "",
        "review_reason": review_reason if review_reason else "",
        "user_action": user_action,
        "user_decision": user_decision,
        "manual_correction_value": str(manual_correction_value) if manual_correction_value is not None else "",
        "decision_reason": decision_reason,
        "before_status": before_status,
        "after_status": after_status,
        "raw_response_id": "",
        "app_version": "Phase5_Step6_prototype"
    }

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

# 再照合の比較結果（ボタン押下後も表示を維持するために保持）
if "rereconciliation_comparison" not in st.session_state:
    st.session_state.rereconciliation_comparison = None

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
    # 防御処理: data が dict でない場合
    if not isinstance(data, dict):
        return ExtractionResult(
            file_name=filename,
            date=None,
            page_number=0,
            daily_report_no="",
            tablet_no="",
            store_code="",
            store_name="",
            staff_name="",
            left_totals=[],
            right_totals=[],
            needs_review=True
        )

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
            # 帳票読み取り処理を実行
            extracted_result = extract_items_from_pdf(pdf_bytes, filename)

            # 戻り値が str である場合の防御処理
            if isinstance(extracted_result, str):
                st.error(f"❌ {filename} の読み取りに失敗しました: 'str' object has no attribute 'get'")
                st.warning(f"戻り値が文字列で返ったため、JSON変換に失敗しました。詳細: {extracted_result[:500]}")
                continue

            # 戻り値が dict でない場合の防御処理
            if not isinstance(extracted_result, dict):
                st.error(f"❌ {filename} の読み取りに失敗しました: 予期しない戻り値型 {type(extracted_result).__name__}")
                continue

            # 抽出結果をExtractionResultに変換
            result = dict_to_extraction_result(extracted_result, filename)
            results.append(result)

        except Exception as e:
            st.error(f"❌ {filename} の読み取りに失敗しました: {str(e)}")
            # エラー詳細をログに出力（開発用）
            import traceback
            st.debug(f"トレースバック:\n{traceback.format_exc()}")

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
                            date_items = list(st.session_state.csv_date_candidates.items())
                            MAX_DATE_COLS = 6
                            if len(date_items) == 0:
                                st.caption("日付候補が見つかりませんでした")
                            elif len(date_items) <= MAX_DATE_COLS:
                                cols = st.columns(len(date_items))
                                for col, (date, count) in zip(cols, date_items):
                                    with col:
                                        st.metric(f"{date}", f"{count}件")
                            else:
                                # 日付が多い場合は列が潰れるため、表形式でコンパクト表示
                                st.caption(f"日付候補が{len(date_items)}件あります（一覧表示）")
                                date_df = pd.DataFrame(
                                    [{"日付": d, "件数": c} for d, c in date_items]
                                )
                                st.dataframe(date_df, use_container_width=True, hide_index=True, height=200)

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

            # CSV内に存在する日付をヒントとして表示
            if st.session_state.csv_date_candidates:
                _candidate_dates = "、".join(str(d) for d in st.session_state.csv_date_candidates.keys())
                st.caption(f"CSV内に存在する日付：{_candidate_dates}")

            target_date = st.date_input(
                "対象営業日",
                value=None,
                label_visibility="collapsed",
                help="CSVに存在する日付を選択してください。該当データがない日付を選ぶと照合対象は0件になります。"
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
        col_btn1, col_btn2, col_btn3 = st.columns(3, gap="large")

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
                            # 検出済みの日付列を優先使用（フォールバック：最後の列）
                            date_col = st.session_state.detected_date_column
                            if not date_col or date_col not in filtered_df.columns:
                                date_col = filtered_df.columns[-1]

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

        with col_btn2:
            pass  # スペーサー

        with col_btn3:
            if st.button("Phase 1照合を実行", use_container_width=True, key="phase1_reconcile_btn", type="secondary"):
                if not pdf_files:
                    st.error("⚠️ FAX帳票PDFを選択してください")
                elif st.session_state.salesforce_records is None:
                    st.error("⚠️ Salesforce CSVを先に読込んでください")
                elif st.session_state.target_business_date is None:
                    st.error("⚠️ 対象営業日を選択してください")
                elif st.session_state.filtered_csv_df is None or len(st.session_state.filtered_csv_df) == 0:
                    st.error("⚠️ 対象営業日に一致するCSVデータがありません")
                else:
                    with st.spinner("🔄 Phase 1最小照合を実行中..."):
                        try:
                            # PDFから帳票読み取り結果を生成
                            extraction_results = extract_results_from_pdfs(pdf_files)

                            if not extraction_results:
                                st.error("PDFの読み取りに失敗しました")
                            else:
                                # Phase 1エンジン初期化
                                @st.cache_resource
                                def load_phase1_engine():
                                    return create_phase1_engine(
                                        'data/master/pdf_csv_field_mapping.csv',
                                        'data/master/store_code_mapping.csv',
                                        'data/master/staff_name_master.csv'
                                    )

                                engine = load_phase1_engine()

                                # Phase 1照合実行
                                phase1_results = []
                                target_date_str = st.session_state.target_business_date.strftime('%Y/%m/%d')
                                filtered_df = st.session_state.filtered_csv_df

                                for extraction in extraction_results:
                                    # ExtractionResult → Phase 1フォーマットに変換
                                    pdf_record = {
                                        'page_no': extraction.page_number,
                                        'store_name': extraction.store_name,
                                        'staff_name': extraction.staff_name,
                                        'tablet_no': extraction.tablet_no,
                                        'data_no': extraction.daily_report_no,
                                        'mapped_values': {}  # 将来拡張: 集計値を追加
                                    }

                                    # Phase 1照合実行
                                    result = engine.reconcile_pdf_with_csv(pdf_record, filtered_df, target_date_str)
                                    result['pdf_file'] = extraction.file_name  # ファイル名追加
                                    phase1_results.append(result)

                                st.session_state.phase1_results = phase1_results
                                st.success(f"✓ {len(phase1_results)}件のPhase 1照合が完了しました")

                        except Exception as e:
                            st.error(f"Phase 1照合処理エラー: {str(e)}")
                            import traceback
                            st.error(traceback.format_exc()[:500])

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

        # ===== 注意文：照合ロジック方針（2026-05-30 片山様回答反映） =====
        with st.container():
            st.warning(
                "⚠️ **照合ロジック方針（2026-05-30 片山様回答反映）:**\n\n"
                "今回のSalesforce CSVには、PDF帳票上のDataNo・TabNo・担当者名に対応する列は出力されないため、"
                "これらをCSVとの直接照合キーには使用しません。\n\n"
                "初期版では、日付、PDF上の店舗名、Salesforce CSV側の取扱店コード、集計欄・商品別数字を中心に照合する方針です。\n\n"
                "PDF側のDataNo・TabNo・担当者名は、確認補助情報および候補提示情報として保持します。\n\n"
                "**集計欄・商品別数字とCSV列の対応は、ジオソリューションズ様からの回答待ちです。**"
            )

        # ===== 結果一覧テーブル =====
        with st.container():
            st.markdown('<div class="section-container">', unsafe_allow_html=True)
            st.markdown('<div class="section-title">照合結果一覧</div>', unsafe_allow_html=True)

            # 全行共通の注記は表の列ではなくキャプションで1回だけ表示（表の横伸びを防止）
            st.caption(
                "※ 全行共通: CSVに日報DataNo/タブレットNo列がないため、PDF側は識別補助情報として保持。"
                "集計値ベース照合は先方確認後に確定。"
            )

            # Step 3: 対象営業日・CSV日付・法人・店舗(取扱コード)・委託会社名・ステータス・確認ステータスを表示
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
                use_container_width=True,
                key="download_reconciliation_result_main"
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
                        st.session_state.rereconciliation_comparison = None
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

                        # 初回結果との比較（キーベース照合）
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

                        # 比較結果を session_state に保持（再描画後も表示を維持・フル幅で表示）
                        st.session_state.rereconciliation_comparison = {
                            "comparison_data": comparison_data,
                            "resolved": resolved_count,
                            "still_mismatch": still_mismatch_count,
                            "still_pending": still_pending_count,
                            "newly_mismatch": newly_mismatch_count,
                            "revised_rows": len(revised_df),
                            "rereconciled_count": len(rereconciled_results),
                        }
                        st.success(f"✓ {len(rereconciled_results)}件の再照合が完了しました")

                except Exception as e:
                    st.error(f"再照合処理エラー: {str(e)}")
                    st.session_state.rereconciliation_comparison = None

        # ===== 再照合の比較結果（フル幅・永続表示）=====
        comparison = st.session_state.rereconciliation_comparison
        if comparison:
            st.markdown('<div style="margin-top: 1rem;"></div>', unsafe_allow_html=True)
            st.markdown("**再照合結果の比較（キーベース照合）**")
            st.caption(
                f"修正後CSV {comparison['revised_rows']}行 / 再照合 {comparison['rereconciled_count']}件 ・ "
                "照合キー（日付＋取扱店コード）で初回と突き合わせています。"
            )

            df_comparison = pd.DataFrame(comparison["comparison_data"])
            st.dataframe(df_comparison, use_container_width=True, height=250)

            # 統計表示
            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4, gap="small")
            with col_stat1:
                st.metric("解消済み", f"{comparison['resolved']}件")
            with col_stat2:
                st.metric("まだ不一致", f"{comparison['still_mismatch']}件")
            with col_stat3:
                st.metric("要確認のまま", f"{comparison['still_pending']}件")
            with col_stat4:
                st.metric("新たに不一致", f"{comparison['newly_mismatch']}件")

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

            # 全行共通の注記は表の列ではなくキャプションで1回だけ表示（表の横伸びを防止）
            st.caption("※ 全行共通: CSVに日報DataNo/タブレットNo列がないため、PDF側は識別補助情報として保持。")

            table_data = []
            for result in results:
                table_data.append({
                    "ファイル名": result.file_name,
                    "対象営業日": str(st.session_state.target_business_date) if st.session_state.target_business_date else "-",
                    "日付": result.extraction.date or "-",
                    "法人・店舗(取扱コード)": result.extraction.store_code or "-",
                    "担当者": result.extraction.staff_name or "-",
                    "ステータス": result.status,
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
                use_container_width=True,
                key="download_reconciliation_result_after_rerun"
            )

    # ===== Phase 1 最小照合結果表示 =====
    if st.session_state.get('phase1_results'):
        from phase1_reconciliation_ui import (
            display_phase1_reconciliation_summary,
            display_phase1_reconciliation_detail,
            create_phase1_detail_csv
        )

        st.markdown("---")
        st.markdown("## Phase 1 最小照合結果")

        phase1_results = st.session_state.phase1_results

        # サマリー表示
        st.markdown("### 照合サマリー")
        display_phase1_reconciliation_summary(phase1_results)

        # 詳細表示
        st.markdown("### 詳細")
        display_phase1_reconciliation_detail(phase1_results)

        # ダウンロードCSV生成
        st.markdown("### ダウンロード")

        csv_content = create_phase1_detail_csv(phase1_results)

        st.download_button(
            label="Phase 1詳細をCSVダウンロード",
            data=csv_content,
            file_name=f"phase1_reconciliation_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="download_phase1_reconciliation_detail"
        )

# ===== Phase 1 最小照合ロジック =====
# この関数は後で定義（モジュール化）

def run_phase1_reconciliation():
    """Phase 1 最小照合ロジック実行"""
    from phase1_reconciliation_ui import (
        display_phase1_reconciliation_summary,
        display_phase1_reconciliation_detail,
        create_phase1_detail_csv
    )

    st.markdown("## Phase 1 最小照合（試験版）")
    st.info("このセクションでは保守的な照合を行います。候補提示と差分理由表示が主目的です。")

    # CSV読込（上のセクションと共通）
    csv_file = st.file_uploader("CSV ファイルを選択", type=["csv"], key="phase1_csv_upload")
    if not csv_file:
        st.warning("CSV ファイルを選択してください")
        return

    try:
        df_csv = pd.read_csv(csv_file, encoding='cp932')
    except UnicodeDecodeError:
        df_csv = pd.read_csv(csv_file, encoding='utf-8')

    st.success(f"CSV読込完了: {len(df_csv)} 行")

    # 対象営業日選択
    target_date = st.date_input("対象営業日", value=pd.Timestamp.today())
    target_date_str = target_date.strftime('%Y/%m/%d')

    # CSV営業日でフィルタ
    # 列283（0-indexed: 282）が営業日
    df_target = df_csv[df_csv.iloc[:, 282] == target_date_str]

    if len(df_target) == 0:
        st.warning(f"対象営業日 {target_date_str} のCSVレコードが見つかりません")
        return

    st.success(f"対象営業日のCSVレコード: {len(df_target)} 件")

    # PDF読込
    pdf_files = st.file_uploader("PDF ファイルを選択", type=["pdf"], accept_multiple_files=True, key="phase1_pdf_upload")
    if not pdf_files:
        st.warning("PDF ファイルを選択してください")
        return

    st.success(f"PDF読込完了: {len(pdf_files)} ファイル")

    # Phase 1エンジン初期化
    @st.cache_resource
    def load_phase1_engine():
        return create_phase1_engine(
            'data/master/pdf_csv_field_mapping.csv',
            'data/master/store_code_mapping.csv',
            'data/master/staff_name_master.csv'
        )

    engine = load_phase1_engine()

    # PDF処理と照合実行
    st.markdown("### 照合処理中...")
    progress_bar = st.progress(0)

    all_results = []
    pdf_names = []

    for pdf_idx, pdf_file in enumerate(pdf_files):
        progress_bar.progress((pdf_idx + 1) / len(pdf_files))

        try:
            # PDF抽出（既存の extractor.extract_items_from_pdf を使用）
            extracted_data = extract_items_from_pdf(pdf_file)

            # 抽出結果が dict の場合（PDF 1ページ = 1帳票）
            if isinstance(extracted_data, dict):
                pdf_record = {
                    'page_no': 1,
                    'store_name': extracted_data.get('store_name'),
                    'staff_name': extracted_data.get('staff_name'),
                    'tablet_no': extracted_data.get('tablet_no'),
                    'data_no': extracted_data.get('data_no'),
                    'mapped_values': extracted_data.get('mapped_values', {})
                }

                # Phase 1照合実行
                result = engine.reconcile_pdf_with_csv(pdf_record, df_target, target_date_str)
                all_results.append(result)
                pdf_names.append(pdf_file.name)

        except Exception as e:
            st.error(f"PDF処理エラー ({pdf_file.name}): {str(e)}")

    progress_bar.empty()

    if not all_results:
        st.error("照合対象のPDFが処理できませんでした")
        return

    # 照合結果表示
    st.markdown("### 照合結果")

    # サマリー表示
    display_phase1_reconciliation_summary(all_results)

    # 詳細表示
    st.markdown("### 詳細")
    display_phase1_reconciliation_detail(all_results)

    # ダウンロードCSV生成
    st.markdown("### ダウンロード")

    csv_content = create_phase1_detail_csv(all_results)

    # ファイル名にpdf_fileを設定
    for idx, (result, pdf_name) in enumerate(zip(all_results, pdf_names)):
        result['pdf_file'] = pdf_name

    csv_content = create_phase1_detail_csv(all_results)

    st.download_button(
        label="照合詳細をダウンロード（CSV）",
        data=csv_content,
        file_name=f"phase1_reconciliation_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        key="download_phase1_reconciliation_detail"
    )

    # ===== Phase 4b: 照合結果確認UI（Phase 1-4a統合） =====
    st.markdown("---")
    st.markdown("## 📊 照合結果確認UI（Phase 4b）")
    st.markdown("Phase 1〜4a の照合結果を確認・検証します")

    from helpers.result_display import (
        format_page_summary_table,
        format_candidate_scores_table,
        format_field_comparison_table,
        generate_download_csv,
    )

    # [1] ページサマリー表示
    st.markdown("### [1] ページ単位の照合結果一覧")

    summary_df = format_page_summary_table(all_results)
    if not summary_df.empty:
        st.dataframe(summary_df, use_container_width=True, hide_index=True)

        # [2] 詳細表示（選択式）
        st.markdown("### [2] 詳細表示")

        if len(summary_df) > 0:
            page_options = summary_df['Page'].tolist()
            selected_page = st.selectbox("詳細を表示するページを選択", options=page_options, key="page_detail_selector")

            if selected_page is not None:
                # 選択したページの結果を取得
                selected_result = all_results[selected_page - 1]

                col1, col2 = st.columns(2, gap="large")

                with col1:
                    st.markdown("#### PDF基本情報")
                    st.write(f"**ページ**: {selected_result.get('page_no', 'N/A')}")
                    st.write(f"**営業日**: {selected_result.get('pdf_date', 'N/A')}")
                    st.write(f"**店舗名**: {selected_result.get('pdf_store_name', 'N/A')}")
                    st.write(f"**取扱コード**: {selected_result.get('store_code', 'N/A')}")
                    st.write(f"**スタッフ**: {selected_result.get('staff_name', 'N/A')}")

                with col2:
                    st.markdown("#### CSV照合結果")
                    st.write(f"**ステータス**: {selected_result.get('status', 'N/A')}")
                    st.write(f"**CSV候補**: {selected_result.get('csv_candidate_count', 0)} 件")
                    field_summary = selected_result.get('field_comparison_summary', {})
                    st.write(f"**比較対象**: {field_summary.get('compared_fields', 0)} / {field_summary.get('total_fields', 0)} 項目")

                # [複数候補表示]
                candidate_scores = selected_result.get('candidate_scores', [])
                if candidate_scores and len(candidate_scores) > 0:
                    st.markdown("#### 複数CSV候補（Phase 4a）")
                    candidate_df = format_candidate_scores_table(candidate_scores)
                    if candidate_df is not None:
                        st.dataframe(candidate_df, use_container_width=True, hide_index=True)

                # [フィールド比較詳細]
                st.markdown("#### フィールド比較詳細（Phase 3）")
                field_comparisons = selected_result.get('field_comparisons', [])
                if field_comparisons:
                    field_df = format_field_comparison_table(field_comparisons)
                    if field_df is not None:
                        st.dataframe(field_df, use_container_width=True, hide_index=True)

        # [3] ダウンロード機能
        st.markdown("### [3] 確認用CSVダウンロード")

        csv_bytes, csv_filename = generate_download_csv(all_results)

        st.download_button(
            label="📥 確認用CSV をダウンロード",
            data=csv_bytes,
            file_name=csv_filename,
            mime="text/csv",
            use_container_width=True,
            key="download_phase4b_csv"
        )
    else:
        st.warning("⚠️ 照合結果がありません")


# ===== [4] AI合計欄V2.2参考判定 =====
st.markdown("### [4] AI合計欄 V2.2 参考判定（補助機能）")

# V2.2並列分類CSVを読み込む
v22_csv_path = Path(__file__).parent / "data" / "test_outputs" / "phase5_ai_tally_v22_parallel_classification.csv"

if v22_csv_path.exists():
    try:
        df_v22 = pd.read_csv(v22_csv_path)

        # 説明文
        st.info(
            "**この判定はAI合計欄に対する補助判定です。** 既存の照合結果を置き換えるものではありません。"
            "自動確定候補と要確認を分け、確認作業を支援します。\n"
            "初期導入では、自動確定候補も含めサンプル確認を推奨します。"
        )

        # KPIサマリー
        st.markdown("#### KPI サマリー")

        total_pages = len(df_v22)
        auto_confirm_count = int(df_v22['auto_confirm_v22'].sum())
        review_required_count = int(df_v22['review_required_v22'].sum())
        low_confidence_count = int((df_v22['confidence'] == 'low').sum())
        ocr_correction_count = int((df_v22['classification'] == 'ocr_correction').sum())
        dual_classification = int(((df_v22['auto_confirm_v22']) & (df_v22['review_required_v22'])).sum())

        col1, col2, col3, col4, col5 = st.columns(5, gap="small")

        with col1:
            st.metric("対象ページ数", total_pages)

        with col2:
            st.metric("✅ 自動確定候補", auto_confirm_count)

        with col3:
            st.metric("⚠️ 要確認", review_required_count)

        with col4:
            st.metric("🔶 低信頼度", low_confidence_count)

        with col5:
            st.metric("🔄 OCR補正", ocr_correction_count)

        # 排他チェック
        st.markdown(f"**排他チェック：** {'✅ OK（重複なし）' if dual_classification == 0 else '⚠️ 重複あり'}")

        # フィルター
        st.markdown("#### フィルター")
        filter_option = st.radio(
            "表示する分類：",
            options=("すべて", "自動確定候補のみ", "要確認のみ", "低信頼度のみ", "OCR補正候補のみ"),
            horizontal=True,
            key="v22_filter"
        )

        # フィルター適用
        if filter_option == "自動確定候補のみ":
            df_filtered = df_v22[df_v22['auto_confirm_v22'] == True].copy()
        elif filter_option == "要確認のみ":
            df_filtered = df_v22[df_v22['review_required_v22'] == True].copy()
        elif filter_option == "低信頼度のみ":
            df_filtered = df_v22[df_v22['confidence'] == 'low'].copy()
        elif filter_option == "OCR補正候補のみ":
            df_filtered = df_v22[df_v22['classification'] == 'ocr_correction'].copy()
        else:
            df_filtered = df_v22.copy()

        # 特別ページの説明
        if len(df_filtered) > 0:
            st.markdown("#### 注目ページ")

            special_pages = {
                "P14": "旧読取34 → 新読取3（CSV=3）｜OCR補正候補 + 自動確定候補",
                "P16": "v3=9、v22=2、CSV=11、confidence=low｜低信頼度 + 要確認（強制確認）",
                "P30": "旧読取2 → 新読取1（CSV=1）｜OCR補正候補 + 自動確定候補"
            }

            for page_id, description in special_pages.items():
                if page_id in df_filtered['page_id'].values:
                    st.write(f"**{page_id}：** {description}")

        # テーブル表示
        st.markdown("#### 詳細テーブル")

        # 表示列を選定
        display_cols = [
            'page_id', 'store_name', 'v3_value', 'v22_value', 'csv_value',
            'confidence', 'classification', 'auto_confirm_v22', 'review_required_v22',
            'review_reasons'
        ]

        df_display = df_filtered[display_cols].copy()

        # 列名を日本語に変更
        df_display.columns = [
            'ページ', '店舗名', 'v3値', 'v22値', 'CSV値',
            '信頼度', '分類', '自動確定', '要確認', '確認理由'
        ]

        # auto_confirm / review_required を ✅/⚠️ に
        df_display['自動確定'] = df_display['自動確定'].apply(lambda x: '✅' if x else '❌')
        df_display['要確認'] = df_display['要確認'].apply(lambda x: '⚠️' if x else '❌')

        st.dataframe(df_display, use_container_width=True, hide_index=True)

        # CSVダウンロード
        st.markdown("#### ダウンロード")

        # V2.2参考判定テーブルをCSV形式で出力
        csv_buffer = io.StringIO()
        df_v22.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        csv_bytes = csv_buffer.getvalue().encode('utf-8-sig')

        st.download_button(
            label="📥 V2.2参考判定 CSV をダウンロード",
            data=csv_bytes,
            file_name="ai_tally_v22_review_flags.csv",
            mime="text/csv",
            use_container_width=True,
            key="download_v22_csv"
        )

        # 注意書き
        st.warning(
            "⚠️ **V2.2は参考判定です。**\n"
            "• 初期導入では、自動確定候補も必要に応じてサンプル確認してください。\n"
            "• CSV不一致、低信頼度、悪化検知は必ず人間確認してください。\n"
            "• 最終決定責任は確認担当者にあります。"
        )

        # ===== 確認ログ操作 =====
        st.divider()
        st.markdown("#### 確認ログ操作")

        # セッションID初期化
        if "confirmation_session_id" not in st.session_state:
            st.session_state.confirmation_session_id = generate_session_id()

        if "confirmation_logs" not in st.session_state:
            st.session_state.confirmation_logs = []

        # 確認者名入力
        operator_name = st.text_input(
            "確認者名",
            value="スタッフA",
            max_chars=50,
            key="confirmation_operator_name"
        )

        # 対象ページ選択
        page_options = []
        for _, row in df_v22.iterrows():
            page_id = row['page_id']
            classification = row.get('classification', '')
            v3_val = row.get('v3_value', '')
            v22_val = row.get('v22_value', '')
            csv_val = row.get('csv_value', '')
            label = f"{page_id} | {classification} | v3={v3_val} / v22={v22_val} / csv={csv_val}"
            page_options.append((page_id, label))

        if len(page_options) > 0:
            selected_page_label = st.selectbox(
                "対象ページを選択",
                options=[label for _, label in page_options],
                key="confirmation_page_select"
            )

            # 選択ページの page_id を取得
            selected_page_id = next(page for page, label in page_options if label == selected_page_label)

            # 選択ページのデータを取得
            selected_row = df_v22[df_v22['page_id'] == selected_page_id].iloc[0]

            # 詳細表示
            st.markdown("**選択ページの詳細**")
            col1, col2, col3 = st.columns(3)

            with col1:
                st.write(f"**ページ:** {selected_row['page_id']}")
                st.write(f"**店舗:** {selected_row.get('store_name', '-')}")
                st.write(f"**分類:** {selected_row.get('classification', '-')}")

            with col2:
                st.write(f"**v3値:** {selected_row.get('v3_value', '-')}")
                st.write(f"**v22値:** {selected_row.get('v22_value', '-')}")
                st.write(f"**CSV値:** {selected_row.get('csv_value', '-')}")

            with col3:
                st.write(f"**信頼度:** {selected_row.get('confidence', '-')}")
                st.write(f"**自動確定:** {'✅' if selected_row.get('auto_confirm_v22') else '❌'}")
                st.write(f"**要確認:** {'⚠️' if selected_row.get('review_required_v22') else '❌'}")

            # before_status を決定
            before_status = "unreviewed"
            if selected_row.get('auto_confirm_v22'):
                before_status = "auto_confirm_candidate"
            elif selected_row.get('review_required_v22'):
                before_status = "review_required"

            # 操作ボタン
            st.markdown("**操作を選択してください**")
            operation = st.radio(
                "対応内容",
                options=[
                    "確認済み（V2.2を採用）",
                    "V2.2を採用",
                    "CSV値を採用",
                    "PDF値を採用",
                    "v3値を採用",
                    "手動修正",
                    "保留",
                    "スキップ"
                ],
                horizontal=True,
                key="confirmation_operation"
            )

            # 手動修正 / PDF値 / 保留 時の入力欄
            manual_correction_value = None
            decision_reason = ""

            if operation in ["手動修正", "PDF値を採用", "保留"]:
                col_input1, col_input2 = st.columns(2)

                with col_input1:
                    if operation == "手動修正":
                        manual_correction_value = st.text_input(
                            "修正後の値",
                            value="",
                            key="confirmation_manual_value"
                        )

                with col_input2:
                    decision_reason = st.text_area(
                        "判定理由 / メモ",
                        value="",
                        height=60,
                        key="confirmation_reason"
                    )

            # 操作実行ボタン
            col_btn1, col_btn2 = st.columns(2)

            with col_btn1:
                if st.button("操作を記録", key="confirmation_confirm_btn"):
                    # ログ行を構築
                    if operation == "確認済み（V2.2を採用）":
                        log_row = build_confirmation_log_row(
                            page=selected_page_id,
                            v3_value=selected_row.get('v3_value'),
                            v22_value=selected_row.get('v22_value'),
                            csv_value=selected_row.get('csv_value'),
                            confidence=selected_row.get('confidence'),
                            classification=selected_row.get('classification'),
                            auto_confirm=selected_row.get('auto_confirm_v22'),
                            review_required=selected_row.get('review_required_v22'),
                            review_reason=selected_row.get('review_reasons', ''),
                            user_action="confirm",
                            user_decision="accept_v22",
                            manual_correction_value=selected_row.get('v22_value'),
                            decision_reason=decision_reason,
                            before_status=before_status,
                            after_status="confirmed",
                            operator_name=operator_name,
                            store_name=selected_row.get('store_name', ''),
                            store_code=selected_row.get('store_code', '')
                        )

                    elif operation == "V2.2を採用":
                        log_row = build_confirmation_log_row(
                            page=selected_page_id,
                            v3_value=selected_row.get('v3_value'),
                            v22_value=selected_row.get('v22_value'),
                            csv_value=selected_row.get('csv_value'),
                            confidence=selected_row.get('confidence'),
                            classification=selected_row.get('classification'),
                            auto_confirm=selected_row.get('auto_confirm_v22'),
                            review_required=selected_row.get('review_required_v22'),
                            review_reason=selected_row.get('review_reasons', ''),
                            user_action="select_v22",
                            user_decision="accept_v22",
                            manual_correction_value=selected_row.get('v22_value'),
                            decision_reason=decision_reason,
                            before_status=before_status,
                            after_status="confirmed",
                            operator_name=operator_name,
                            store_name=selected_row.get('store_name', ''),
                            store_code=selected_row.get('store_code', '')
                        )

                    elif operation == "CSV値を採用":
                        log_row = build_confirmation_log_row(
                            page=selected_page_id,
                            v3_value=selected_row.get('v3_value'),
                            v22_value=selected_row.get('v22_value'),
                            csv_value=selected_row.get('csv_value'),
                            confidence=selected_row.get('confidence'),
                            classification=selected_row.get('classification'),
                            auto_confirm=selected_row.get('auto_confirm_v22'),
                            review_required=selected_row.get('review_required_v22'),
                            review_reason=selected_row.get('review_reasons', ''),
                            user_action="select_csv",
                            user_decision="accept_csv",
                            manual_correction_value=selected_row.get('csv_value'),
                            decision_reason=decision_reason,
                            before_status=before_status,
                            after_status="confirmed",
                            operator_name=operator_name,
                            store_name=selected_row.get('store_name', ''),
                            store_code=selected_row.get('store_code', '')
                        )

                    elif operation == "PDF値を採用":
                        log_row = build_confirmation_log_row(
                            page=selected_page_id,
                            v3_value=selected_row.get('v3_value'),
                            v22_value=selected_row.get('v22_value'),
                            csv_value=selected_row.get('csv_value'),
                            confidence=selected_row.get('confidence'),
                            classification=selected_row.get('classification'),
                            auto_confirm=selected_row.get('auto_confirm_v22'),
                            review_required=selected_row.get('review_required_v22'),
                            review_reason=selected_row.get('review_reasons', ''),
                            user_action="select_pdf",
                            user_decision="accept_pdf",
                            manual_correction_value=manual_correction_value,
                            decision_reason=decision_reason,
                            before_status=before_status,
                            after_status="confirmed",
                            operator_name=operator_name,
                            store_name=selected_row.get('store_name', ''),
                            store_code=selected_row.get('store_code', '')
                        )

                    elif operation == "v3値を採用":
                        log_row = build_confirmation_log_row(
                            page=selected_page_id,
                            v3_value=selected_row.get('v3_value'),
                            v22_value=selected_row.get('v22_value'),
                            csv_value=selected_row.get('csv_value'),
                            confidence=selected_row.get('confidence'),
                            classification=selected_row.get('classification'),
                            auto_confirm=selected_row.get('auto_confirm_v22'),
                            review_required=selected_row.get('review_required_v22'),
                            review_reason=selected_row.get('review_reasons', ''),
                            user_action="select_v3",
                            user_decision="accept_v3",
                            manual_correction_value=selected_row.get('v3_value'),
                            decision_reason=decision_reason,
                            before_status=before_status,
                            after_status="confirmed",
                            operator_name=operator_name,
                            store_name=selected_row.get('store_name', ''),
                            store_code=selected_row.get('store_code', '')
                        )

                    elif operation == "手動修正":
                        log_row = build_confirmation_log_row(
                            page=selected_page_id,
                            v3_value=selected_row.get('v3_value'),
                            v22_value=selected_row.get('v22_value'),
                            csv_value=selected_row.get('csv_value'),
                            confidence=selected_row.get('confidence'),
                            classification=selected_row.get('classification'),
                            auto_confirm=selected_row.get('auto_confirm_v22'),
                            review_required=selected_row.get('review_required_v22'),
                            review_reason=selected_row.get('review_reasons', ''),
                            user_action="correct",
                            user_decision="manual_correct",
                            manual_correction_value=manual_correction_value,
                            decision_reason=decision_reason,
                            before_status=before_status,
                            after_status="corrected",
                            operator_name=operator_name,
                            store_name=selected_row.get('store_name', ''),
                            store_code=selected_row.get('store_code', '')
                        )

                    elif operation == "保留":
                        log_row = build_confirmation_log_row(
                            page=selected_page_id,
                            v3_value=selected_row.get('v3_value'),
                            v22_value=selected_row.get('v22_value'),
                            csv_value=selected_row.get('csv_value'),
                            confidence=selected_row.get('confidence'),
                            classification=selected_row.get('classification'),
                            auto_confirm=selected_row.get('auto_confirm_v22'),
                            review_required=selected_row.get('review_required_v22'),
                            review_reason=selected_row.get('review_reasons', ''),
                            user_action="defer",
                            user_decision="needs_follow_up",
                            manual_correction_value=None,
                            decision_reason=decision_reason,
                            before_status=before_status,
                            after_status="deferred",
                            operator_name=operator_name,
                            store_name=selected_row.get('store_name', ''),
                            store_code=selected_row.get('store_code', '')
                        )

                    elif operation == "スキップ":
                        log_row = build_confirmation_log_row(
                            page=selected_page_id,
                            v3_value=selected_row.get('v3_value'),
                            v22_value=selected_row.get('v22_value'),
                            csv_value=selected_row.get('csv_value'),
                            confidence=selected_row.get('confidence'),
                            classification=selected_row.get('classification'),
                            auto_confirm=selected_row.get('auto_confirm_v22'),
                            review_required=selected_row.get('review_required_v22'),
                            review_reason=selected_row.get('review_reasons', ''),
                            user_action="skip",
                            user_decision="skip",
                            manual_correction_value=None,
                            decision_reason=decision_reason,
                            before_status=before_status,
                            after_status="skipped",
                            operator_name=operator_name,
                            store_name=selected_row.get('store_name', ''),
                            store_code=selected_row.get('store_code', '')
                        )

                    # セッションログに追加
                    st.session_state.confirmation_logs.append(log_row)

                    st.success(f"✅ ログを記録しました ({len(st.session_state.confirmation_logs)}件)")

        # ログ一覧表示
        if len(st.session_state.confirmation_logs) > 0:
            st.markdown("#### 確認ログ一覧")

            # ログをDataFrameに変換
            df_logs = pd.DataFrame(st.session_state.confirmation_logs)

            # 表示列を選定
            display_log_cols = [
                'timestamp', 'operator_name', 'page', 'user_action', 'user_decision',
                'final_value', 'before_status', 'after_status', 'decision_reason'
            ]

            df_logs_display = df_logs[display_log_cols].copy()

            # 列名を日本語に
            df_logs_display.columns = [
                '記録時刻', '確認者', 'ページ', '操作', '判定',
                '最終値', '操作前', '操作後', '理由'
            ]

            st.dataframe(df_logs_display, use_container_width=True, hide_index=True)

            # ログCSVダウンロード
            st.markdown("#### ログダウンロード")

            csv_buffer = io.StringIO()
            df_logs.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
            csv_bytes = csv_buffer.getvalue().encode('utf-8-sig')

            st.download_button(
                label="📥 確認ログ CSV をダウンロード",
                data=csv_bytes,
                file_name=f"ai_tally_v22_confirmation_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
                key="download_confirmation_logs"
            )

    except Exception as e:
        st.error(f"❌ V2.2参考判定の読み込みに失敗しました：{e}")
else:
    st.warning(
        "⚠️ **AI合計欄V2.2参考表示データが見つかりません。**\n"
        "先に並列分類を実行してください。\n"
        "`python scripts/apply_ai_tally_v22_classification_to_all30.py`"
    )


# ===== フッター =====
st.markdown("""
<div style="background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 6px; padding: 0.75rem; margin-top: 2rem;">
<small>
⚠️ <b>この画面は試作版です。</b><br>
実際の読み取り精度は、実FAX帳票PDFと実Salesforce CSVでの検証後に調整します。<br>
AI合計欄V2.2判定は条件付き採用候補です。確認支援ツールとしてご利用ください。
</small>
</div>
""", unsafe_allow_html=True)
