"""
帳票読取・確認画面（試作版）
Streamlit アプリケーション
"""

import os
import json
import base64
import csv
from datetime import datetime
from pathlib import Path
import tempfile

import streamlit as st
import fitz  # PyMuPDF
from PIL import Image
from dotenv import load_dotenv

from extractor import extract_items_from_image, validate_extraction_result

# 環境変数読込
load_dotenv()

# ページ設定
st.set_page_config(
    page_title="帳票読取・確認画面",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ===== CSS カスタマイズ =====
st.markdown("""
<style>
    .main {
        padding: 1rem;
    }
    .stButton button {
        width: 100%;
        margin-bottom: 0.5rem;
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
</style>
""", unsafe_allow_html=True)

# ===== セッション状態の初期化 =====
if "pdf_bytes" not in st.session_state:
    st.session_state.pdf_bytes = None
if "pdf_pages" not in st.session_state:
    st.session_state.pdf_pages = []
if "extraction_result" not in st.session_state:
    st.session_state.extraction_result = {
        "処理日": None,
        "店舗名": None,
        "担当者名": None,
        "件数": None,
        "合計値": None,
        "備考": None
    }
if "filename" not in st.session_state:
    st.session_state.filename = None

# ===== メイン画面 =====
st.markdown('<div class="title-text">帳票読取・確認画面（試作版）</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle-text">FAX由来の帳票データから必要項目を抽出します</div>', unsafe_allow_html=True)

# ===== アップロード欄 =====
st.markdown("### 帳票ファイルをアップロード")
st.markdown("PDFファイルを選択してください（初期版では1ファイルずつ確認する想定です）")

uploaded_file = st.file_uploader(
    "ファイルを選択",
    type=["pdf"],
    label_visibility="collapsed"
)

# ===== 2カラムレイアウト =====
if uploaded_file is not None:
    # ファイル情報を保存
    st.session_state.pdf_bytes = uploaded_file.read()
    st.session_state.filename = uploaded_file.name

    # PDFをページに分割（PyMuPDF使用）
    try:
        doc = fitz.open(stream=st.session_state.pdf_bytes, filetype="pdf")
        pages = []
        for page in doc:
            # 高解像度でレンダリング（2倍ズーム）
            mat = fitz.Matrix(2, 2)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pages.append(img)
        doc.close()
        st.session_state.pdf_pages = pages
        st.success("ファイルを読み込みました")
    except Exception as e:
        st.error(f"PDFファイルの読み込みに失敗しました: {str(e)}")
        st.session_state.pdf_pages = []

# PDFが読み込まれた場合、2カラムレイアウトを表示
if st.session_state.pdf_pages:
    col_left, col_right = st.columns([1, 1])

    # ===== 左側：PDFプレビュー =====
    with col_left:
        st.markdown("### 帳票プレビュー")
        st.markdown("アップロードした帳票を確認できます")

        # ページ表示
        page_num = st.slider(
            "ページ選択",
            1,
            len(st.session_state.pdf_pages),
            1,
            label_visibility="collapsed"
        )

        # PDF画像表示
        if st.session_state.pdf_pages:
            st.image(
                st.session_state.pdf_pages[page_num - 1],
                caption=f"ページ {page_num} / {len(st.session_state.pdf_pages)}",
                use_container_width=True
            )

    # ===== 右側：抽出結果フォーム =====
    with col_right:
        st.markdown("### 抽出結果")
        st.markdown("AI/OCRで抽出した内容です。必要に応じて修正してください")

        # 初回読取（AIで自動抽出）
        if st.button("帳票を解析", key="extract_btn", use_container_width=True):
            with st.spinner("帳票を解析しています…"):
                # ページ画像をBase64エンコード
                current_page = st.session_state.pdf_pages[page_num - 1]

                # PIL Image を JPEG バイトに変換
                import io
                buffer = io.BytesIO()
                current_page.save(buffer, format="JPEG")
                image_bytes = buffer.getvalue()
                image_base64 = base64.b64encode(image_bytes).decode("utf-8")

                # Claude Vision で抽出
                result = extract_items_from_image(image_base64)

                # エラーチェック
                if "error" in result:
                    st.warning(f"一部の項目を抽出できませんでした。必要に応じて手動で修正してください。\nエラー: {result['error']}")
                else:
                    st.success("抽出が完了しました。内容をご確認ください")

                # 結果を検証・正規化
                st.session_state.extraction_result = validate_extraction_result(result)

        # ===== フォーム表示・編集 =====
        st.markdown("#### 抽出結果（編集可能）")

        col1, col2 = st.columns(2)
        with col1:
            st.session_state.extraction_result["処理日"] = st.text_input(
                "処理日",
                value=st.session_state.extraction_result.get("処理日") or "",
                placeholder="例）2026-05-05",
                help="日付をYYYY-MM-DD形式で入力"
            ) or None

            st.session_state.extraction_result["店舗名"] = st.text_input(
                "店舗名",
                value=st.session_state.extraction_result.get("店舗名") or "",
                placeholder="例）渋谷店"
            ) or None

            st.session_state.extraction_result["担当者名"] = st.text_input(
                "担当者名",
                value=st.session_state.extraction_result.get("担当者名") or "",
                placeholder="例）山田 太郎"
            ) or None

        with col2:
            try:
                件数_val = st.session_state.extraction_result.get("件数")
                件数_display = int(件数_val) if 件数_val is not None else None
            except (ValueError, TypeError):
                件数_display = None

            st.session_state.extraction_result["件数"] = st.number_input(
                "件数",
                value=件数_display,
                step=1,
                min_value=0,
                format="%d" if 件数_display is not None else None
            )

            try:
                合計値_val = st.session_state.extraction_result.get("合計値")
                合計値_display = int(合計値_val) if 合計値_val is not None else None
            except (ValueError, TypeError):
                合計値_display = None

            st.session_state.extraction_result["合計値"] = st.number_input(
                "合計値",
                value=合計値_display,
                step=1,
                min_value=0,
                format="%d" if 合計値_display is not None else None
            )

        # 備考
        st.session_state.extraction_result["備考"] = st.text_area(
            "備考",
            value=st.session_state.extraction_result.get("備考") or "",
            placeholder="必要に応じて備考を入力",
            height=60
        ) or None

        st.markdown("""
        <div class="info-text">
        ※ 抽出結果は原本を確認のうえ必要に応じて修正してください
        </div>
        """, unsafe_allow_html=True)

# ===== 下部：出力ボタン =====
st.markdown("---")
st.markdown("### 出力・保存")

col1, col2, col3 = st.columns(3)

with col1:
    if st.button("保存する", key="save_btn", use_container_width=True):
        # JSON で保存
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path("outputs") / f"result_{timestamp}.json"

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "filename": st.session_state.filename,
            "data": st.session_state.extraction_result
        }

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        st.success(f"内容を保存しました: {output_file}")

with col2:
    if st.button("CSVで出力", key="csv_btn", use_container_width=True):
        # CSV で出力
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = Path("outputs") / f"result_{timestamp}.csv"

        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=st.session_state.extraction_result.keys())
            writer.writeheader()
            writer.writerow(st.session_state.extraction_result)

        st.success(f"CSVファイルを出力しました: {output_file}")

with col3:
    # ダウンロード用
    if st.session_state.extraction_result:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # CSV データをメモリに作成
        import io
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=st.session_state.extraction_result.keys())
        writer.writeheader()
        writer.writerow(st.session_state.extraction_result)
        csv_data = csv_buffer.getvalue()

        st.download_button(
            label="CSVをダウンロード",
            data=csv_data,
            file_name=f"result_{timestamp}.csv",
            mime="text/csv"
        )

st.markdown("""
<div class="info-text">
※ 本画面は帳票読取結果を確認するための試作版です
</div>
""", unsafe_allow_html=True)
