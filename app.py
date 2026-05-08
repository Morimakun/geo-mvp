"""
FAX帳票 × Salesforce CSV 照合確認画面（Phase 5：UI統合版）
Streamlit アプリケーション

照合ロジックは reconciliation.py に分離済み
このアプリはCSV照合をメイン機能として提供
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
    ExtractionResult,
    SalesforceRecord
)

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
        border-radius: 4px;
    }
    .info-box {
        background-color: #e7f3ff;
        border-left: 4px solid #2196F3;
        padding: 0.75rem;
        margin: 0.5rem 0;
        border-radius: 4px;
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

# ===== メイン画面 =====
st.markdown('<div class="title-text">FAX帳票 × Salesforce 照合システム</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle-text">帳票読み取り結果とSalesforceデータを自動照合確認します</div>', unsafe_allow_html=True)

# ===== タブを使用してメイン機能を分ける =====
tab1, tab2 = st.tabs(["CSV照合", "PDFから抽出"])

# ===== Tab 1: CSV照合（メイン機能） =====
with tab1:
    st.markdown("### CSVファイルアップロード")

    col1, col2 = st.columns(2)

    # 左列：Salesforce CSV
    with col1:
        st.markdown("**1. Salesforce CSV**")
        st.markdown('<div class="info-box">店舗日報の基準データ（日付、店舗、スタッフ、DataNo、TabNo など）</div>', unsafe_allow_html=True)

        salesforce_file = st.file_uploader(
            "Salesforce CSVを選択",
            type=["csv"],
            key="salesforce_uploader",
            label_visibility="collapsed"
        )

        if salesforce_file is not None:
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                    tmp.write(salesforce_file.getvalue().decode('utf-8'))
                    tmp_path = tmp.name

                st.session_state.salesforce_records = load_salesforce_csv(tmp_path)
                st.success(f"OK: {len(st.session_state.salesforce_records)}件のSalesforceレコードを読込")

                # プレビュー
                with st.expander("CSVプレビュー"):
                    df = pd.read_csv(salesforce_file)
                    st.dataframe(df.head(10), use_container_width=True)
            except Exception as e:
                st.error(f"読込エラー: {str(e)}")

    # 右列：帳票読み取り結果CSV
    with col2:
        st.markdown("**2. 帳票読み取り結果CSV**")
        st.markdown('<div class="info-box">帳票から読み取ったFAX帳票の項目（日付、店舗、スタッフ、データなど）</div>', unsafe_allow_html=True)

        extraction_file = st.file_uploader(
            "抽出結果CSVを選択",
            type=["csv"],
            key="extraction_uploader",
            label_visibility="collapsed"
        )

        if extraction_file is not None:
            try:
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False, encoding='utf-8') as tmp:
                    tmp.write(extraction_file.getvalue().decode('utf-8'))
                    tmp_path = tmp.name

                st.session_state.extraction_results = load_extraction_results(tmp_path)
                st.success(f"OK: {len(st.session_state.extraction_results)}件の抽出結果を読込")

                # プレビュー
                with st.expander("CSVプレビュー"):
                    df = pd.read_csv(extraction_file)
                    st.dataframe(df.head(10), use_container_width=True)
            except Exception as e:
                st.error(f"読込エラー: {str(e)}")

    st.divider()

    # ===== サンプルデータボタン =====
    st.markdown("### またはサンプルデータで試す")

    if st.button("サンプルデータを読込", key="sample_data_btn", use_container_width=True):
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

            st.success(f"OK: サンプルデータを読込完了")
            st.info(f"Salesforce: {len(st.session_state.salesforce_records)}件 | 帳票読み取り結果: {len(st.session_state.extraction_results)}件")
        except Exception as e:
            st.error(f"サンプルデータ読込エラー: {str(e)}")

    st.divider()

    # ===== 照合実行 =====
    st.markdown("### 照合を実行")

    if st.button("照合を実行", key="reconcile_btn", use_container_width=True, type="primary"):
        if st.session_state.salesforce_records is None:
            st.error("Salesforce CSVを先に読込んでください")
        elif st.session_state.extraction_results is None:
            st.error("帳票読み取り結果CSVを先に読込んでください")
        else:
            with st.spinner("照合処理を実行中..."):
                try:
                    results = []
                    for extraction in st.session_state.extraction_results:
                        result = reconcile(extraction, st.session_state.salesforce_records)
                        results.append(result)

                    st.session_state.reconciliation_results = results
                    st.success(f"OK: {len(results)}件の照合が完了しました")
                except Exception as e:
                    st.error(f"照合処理エラー: {str(e)}")

    # ===== 照合結果表示 =====
    if st.session_state.reconciliation_results:
        st.divider()
        st.markdown("### 照合結果")

        results = st.session_state.reconciliation_results

        # 統計情報
        status_counts = {}
        for result in results:
            status = result.status
            status_counts[status] = status_counts.get(status, 0) + 1

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("照合対象", len(results))
        with col2:
            st.metric("一致", status_counts.get("一致", 0))
        with col3:
            st.metric("不一致", status_counts.get("不一致", 0))
        with col4:
            st.metric("要確認", status_counts.get("要確認", 0))

        # 補足指標
        with st.expander("詳細指標"):
            csv_auto_match = sum(1 for r in results if r.matching_key != "見つかりませんでした" and "複数候補" not in r.matching_key)
            csv_candidate_found = sum(1 for r in results if r.matched_record is not None or r.matching_key.startswith("複合キー"))

            col1, col2 = st.columns(2)
            with col1:
                st.metric("CSV行自動特定成功", f"{csv_auto_match}件", f"{csv_auto_match}/{len(results)}")
            with col2:
                st.metric("CSV候補検出成功", f"{csv_candidate_found}件", f"{csv_candidate_found}/{len(results)}")

        # 結果テーブル
        st.markdown("#### 詳細一覧")

        table_data = []
        for result in results:
            table_data.append({
                "ファイル": result.file_name,
                "マッチング": result.matching_key,
                "日付": result.extraction.date or "-",
                "店舗": result.extraction.store_name or "-",
                "スタッフ": result.extraction.staff_name or "-",
                "ステータス": result.status,
            })

        df = pd.DataFrame(table_data)

        # ステータスを色分けして表示
        def highlight_status(val):
            if val == "一致":
                return "background-color: #d4edda; color: #155724; font-weight: bold;"
            elif val == "不一致":
                return "background-color: #f8d7da; color: #721c24; font-weight: bold;"
            elif val == "要確認":
                return "background-color: #fff3cd; color: #856404; font-weight: bold;"
            return ""

        # ステータス列を色付け
        def style_status(s):
            return s.apply(lambda val: highlight_status(val) if val == s.name else "")

        styled_df = df.style.map(
            lambda val: highlight_status(val) if isinstance(val, str) and val in ["一致", "不一致", "要確認"] else "",
            subset=["ステータス"]
        )

        st.dataframe(styled_df, use_container_width=True, height=400)

        # 詳細確認
        st.markdown("#### 詳細確認")

        selected_idx = st.selectbox(
            "詳細を確認する項目を選択",
            range(len(results)),
            format_func=lambda i: f"{results[i].file_name} - {results[i].status}"
        )

        if selected_idx is not None:
            result = results[selected_idx]

            st.markdown(f"**ファイル**: {result.file_name}")
            st.markdown(f"**マッチング方式**: {result.matching_key}")
            st.markdown(f"**ステータス**: {result.status}")

            col1, col2 = st.columns(2)

            with col1:
                st.markdown("**帳票読み取り結果**")
                st.write(f"日付: {result.extraction.date}")
                st.write(f"店舗: {result.extraction.store_name}")
                st.write(f"スタッフ: {result.extraction.staff_name}")
                st.write(f"DataNo: {result.extraction.daily_report_no}")
                st.write(f"TabNo: {result.extraction.tablet_no}")
                st.write(f"左下合計: {'/'.join(result.extraction.left_totals) if result.extraction.left_totals else '-'}")
                st.write(f"右下合計: {'/'.join(result.extraction.right_totals) if result.extraction.right_totals else '-'}")

            with col2:
                st.markdown("**Salesforceレコード**")
                if result.matched_record:
                    st.write(f"日付: {result.matched_record.date}")
                    st.write(f"店舗: {result.matched_record.store_name}")
                    st.write(f"スタッフ: {result.matched_record.staff_name}")
                    st.write(f"DataNo: {result.matched_record.daily_report_no}")
                    st.write(f"TabNo: {result.matched_record.tablet_no}")
                    left_totals = result.matched_record.get_left_totals()
                    right_totals = result.matched_record.get_right_totals()
                    st.write(f"左下合計: {'/'.join(left_totals)}")
                    st.write(f"右下合計: {'/'.join(right_totals)}")
                else:
                    st.warning("対応するレコードが見つかりません")

            # 差分表示
            if result.differences:
                st.markdown("**差分内容**")
                for diff in result.differences:
                    st.markdown(f'<div class="diff-highlight">{diff}</div>', unsafe_allow_html=True)

            # 確認理由表示
            if result.review_reasons:
                st.markdown("**確認理由**")
                for reason in result.review_reasons:
                    st.info(reason)

        st.divider()

        # ===== 結果ダウンロード =====
        st.markdown("### 結果をダウンロード")

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
                result.matching_key,
                result.extraction.date or "",
                result.extraction.store_name or "",
                result.extraction.staff_name or "",
                result.extraction.daily_report_no or "",
                result.extraction.tablet_no or "",
                "/".join(result.extraction.left_totals) if result.extraction.left_totals else "",
                "/".join(result.extraction.right_totals) if result.extraction.right_totals else "",
                result.matched_record.date if result.matched_record else "",
                result.matched_record.store_name if result.matched_record else "",
                result.matched_record.staff_name if result.matched_record else "",
                result.matched_record.daily_report_no if result.matched_record else "",
                result.matched_record.tablet_no if result.matched_record else "",
                "/".join(result.matched_record.get_left_totals()) if result.matched_record else "",
                "/".join(result.matched_record.get_right_totals()) if result.matched_record else "",
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

# ===== Tab 2: PDFから抽出（従来機能）=====
with tab2:
    st.markdown("### PDFファイル処理（試作版）")
    st.info("このタブはPDFファイルから項目を抽出する従来機能です。")
    st.markdown("""
    **使い方:**
    1. Salesforce CSVをアップロード
    2. PDFファイルを複数選択
    3. 照合を実行
    4. 結果を確認・ダウンロード
    """)
    st.warning("⚠️ 現在このタブは実装準備中です。CSV照合タブをご使用ください。")

st.divider()

# ===== フッター =====
st.markdown("""
<div style="text-align: center; color: #999; font-size: 12px; margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #eee;">
※ 本画面はPhase 5（UI統合版）です。<br>
※ 照合ロジックはreconciliation.pyに分離されており、直接importして使用できます。<br>
※ 抽出結果は原本を確認のうえ必要に応じて修正してください。
</div>
""", unsafe_allow_html=True)
