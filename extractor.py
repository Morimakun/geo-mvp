"""Claude Vision API を使用した帳票項目抽出・CSV照合モジュール

【実装方針】
実帳票は複雑な構造を持つため、領域分割アプローチで段階的に抽出します。
1. ヘッダー領域（日付、店舗名、氏名）
2. 下部識別子領域（日報データNo、タブレットNo）
3. 合計欄領域（左下、右下の合計値）
4. 手書きカウント欄（各セルの件数推定）
"""

import json
import os
from typing import Optional, Dict, List
import base64
import fitz  # PyMuPDF
from PIL import Image
from anthropic import Anthropic
from dotenv import load_dotenv

# 環境変数読込（.envファイルから）
load_dotenv(override=True)

# Claude API クライアント初期化
client = Anthropic()

HEADER_EXTRACTION_PROMPT = """以下は帳票の上部ヘッダー領域です。
以下の3項目を抽出してJSON形式で返してください。

抽出対象：
1. date（日付、フォーマット：YYYY-MM-DD）
2. store（店舗名、テキスト）
3. name（氏名、テキスト）

回答例：
{
  "date": "2026-04-20",
  "store": "イオンモール神戸北",
  "name": "山田光子"
}

注意：
- 見つからない項目は null
- 必ずJSON形式のみ"""

ID_EXTRACTION_PROMPT = """以下は帳票の下部識別子領域です。
以下の2項目を抽出してJSON形式で返してください。

抽出対象：
1. data_no（日報データNo、英数字）
2. tab_no（タブレットNo、英数字または記号）

回答例：
{
  "data_no": "005",
  "tab_no": "1い~2002201"
}

注意：
- 見つからない項目は null
- 必ずJSON形式のみ"""

TOTAL_EXTRACTION_PROMPT = """以下は帳票の合計欄です。
数値を抽出してJSON形式で返してください。

抽出対象：
1. total_left（左下の合計値）
2. total_right（右下の合計値）

回答例：
{
  "total_left": 333,
  "total_right": 35.3
}

注意：
- 見つからない項目は null
- 小数点を含む場合も数値で返す
- 必ずJSON形式のみ"""

COUNT_EXTRACTION_PROMPT = """以下は帳票の手書き/チェック欄です。
件数推定をしてJSON形式で返してください。

抽出対象：
各セルの件数推定（手書き線、チェック、数字から推定）

回答例：
{
  "estimated_count": 5,
  "confidence": "high",
  "notes": "5本の手書き線が確認できる"
}

注意：
- 推定値なので確度を confidence で示す (high/medium/low)
- 不鮮明な場合は low を選択
- 必ずJSON形式のみ"""


def extract_items_from_pdf(pdf_bytes: bytes, filename: str) -> Dict:
    """
    PDFから帳票項目を抽出する

    Args:
        pdf_bytes: PDFファイルのバイト列
        filename: ファイル名（ログ用）

    Returns:
        抽出結果を含む辞書
    """
    try:
        # PDFの最初のページを画像化
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        if len(doc) == 0:
            raise ValueError("PDFにページが含まれていません")

        # 最初のページのみ処理
        page = doc[0]
        mat = fitz.Matrix(2, 2)  # 2倍ズーム
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # 画像をBase64エンコード
        import io
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        # Claude Vision で抽出
        message = client.messages.create(
            model="claude-sonnet-4-6",  # Latest Claude Sonnet with Vision API support
            max_tokens=1024,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/jpeg",
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": EXTRACTION_PROMPT
                        }
                    ],
                }
            ],
        )

        # レスポンス解析
        response_text = message.content[0].text

        # JSON抽出
        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text.strip()

            result = json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            result = {
                "date": None,
                "store": None,
                "name": None,
                "data_no": None,
                "tab_no": None,
                "count": None,
                "total": None,
                "notes": None,
                "error": "Failed to parse JSON response"
            }

        # 結果を正規化
        normalized = validate_extraction_result(result)

        # PDF プレビュー画像を含める（詳細表示用）
        normalized['pdf_preview'] = img
        normalized['filename'] = filename

        doc.close()

        return normalized

    except Exception as e:
        return {
            "date": None,
            "store": None,
            "name": None,
            "data_no": None,
            "tab_no": None,
            "count": None,
            "total": None,
            "notes": None,
            "filename": filename,
            "error": str(e)
        }


def validate_extraction_result(data: Dict) -> Dict:
    """
    抽出結果を検証し、型を正規化する

    Args:
        data: 抽出結果

    Returns:
        正規化されたデータ
    """
    validated = {}

    # 文字列フィールド
    for field in ["date", "store", "name", "data_no", "tab_no", "notes"]:
        validated[field] = data.get(field)
        if validated[field] is not None:
            validated[field] = str(validated[field]).strip()
            if validated[field] == "":
                validated[field] = None

    # 数値フィールド
    for field in ["count", "total"]:
        try:
            value = data.get(field)
            if value is not None:
                validated[field] = int(float(value))
            else:
                validated[field] = None
        except (ValueError, TypeError):
            validated[field] = None

    return validated


def match_with_csv(extraction_results: List[Dict], csv_data) -> List[Dict]:
    """
    抽出結果をCSVと照合する

    Args:
        extraction_results: 抽出結果のリスト
        csv_data: Pandas DataFrame (Salesforce CSV)

    Returns:
        照合結果のリスト
    """
    matching_results = []

    # CSV のカラム名を小文字・標準化
    csv_columns = {col.lower(): col for col in csv_data.columns}

    for extracted in extraction_results:
        if "error" in extracted:
            # 抽出エラーの場合は要確認
            result = {
                "filename": extracted.get("filename"),
                "date": extracted.get("date"),
                "store": extracted.get("store"),
                "name": extracted.get("name"),
                "data_no": extracted.get("data_no"),
                "tab_no": extracted.get("tab_no"),
                "extracted_count": extracted.get("count"),
                "csv_count": None,
                "status": "要確認",
                "reason": extracted.get("error"),
                "extracted": extracted,
                "csv_record": None,
                "diffs": [],
                "pdf_preview": extracted.get("pdf_preview"),
            }
            matching_results.append(result)
            continue

        # 照合キーの優先順位
        matched_record = None
        match_key = None

        # ① 日報DataNo で完全一致
        if extracted.get("data_no"):
            candidates = csv_data[
                csv_data.apply(
                    lambda row: str(row.get("日報データNo", "")).strip() == extracted["data_no"].strip(),
                    axis=1
                )
            ]
            if len(candidates) == 1:
                matched_record = candidates.iloc[0]
                match_key = "data_no"
            elif len(candidates) > 1:
                # 複数マッチの場合は要確認
                matched_record = None
                match_key = None

        # ② TabNo で照合（DataNo がない場合）
        if matched_record is None and extracted.get("tab_no"):
            candidates = csv_data[
                csv_data.apply(
                    lambda row: str(row.get("タブレットNo", "")).strip() == extracted["tab_no"].strip(),
                    axis=1
                )
            ]
            if len(candidates) == 1:
                matched_record = candidates.iloc[0]
                match_key = "tab_no"

        # ③ 日付 + 店舗名 + 氏名 で複合照合
        if matched_record is None and all([
            extracted.get("date"),
            extracted.get("store"),
            extracted.get("name")
        ]):
            candidates = csv_data[
                csv_data.apply(
                    lambda row: (
                        str(row.get("日付", "")).strip() == extracted["date"].strip() and
                        str(row.get("店舗名", "")).strip() == extracted["store"].strip() and
                        str(row.get("氏名", "")).strip() == extracted["name"].strip()
                    ),
                    axis=1
                )
            ]
            if len(candidates) == 1:
                matched_record = candidates.iloc[0]
                match_key = "composite"

        # 照合結果の判定
        status = "要確認"
        diffs = []
        csv_record_dict = None

        if matched_record is not None:
            # CSV レコードを辞書に変換
            csv_record_dict = matched_record.to_dict()

            # 差分検出：件数と合計値を確認
            extracted_count = extracted.get("count")
            csv_count = csv_record_dict.get("件数")
            extracted_total = extracted.get("total")
            csv_total = csv_record_dict.get("合計値")

            # 型変換
            try:
                if csv_count is not None:
                    csv_count = int(csv_count)
            except (ValueError, TypeError):
                csv_count = None

            try:
                if csv_total is not None:
                    csv_total = int(csv_total)
            except (ValueError, TypeError):
                csv_total = None

            # 差分判定
            if extracted_count is not None and csv_count is not None:
                if extracted_count != csv_count:
                    diffs.append({
                        "field": "件数",
                        "extracted": extracted_count,
                        "csv": csv_count
                    })

            if extracted_total is not None and csv_total is not None:
                if extracted_total != csv_total:
                    diffs.append({
                        "field": "合計値",
                        "extracted": extracted_total,
                        "csv": csv_total
                    })

            # ステータス判定
            if len(diffs) == 0:
                status = "一致"
            else:
                status = "不一致"
        else:
            # 照合キーが見つからない場合
            status = "要確認"
            csv_count = None

        # 結果作成
        result = {
            "filename": extracted.get("filename"),
            "date": extracted.get("date"),
            "store": extracted.get("store"),
            "name": extracted.get("name"),
            "data_no": extracted.get("data_no"),
            "tab_no": extracted.get("tab_no"),
            "extracted_count": extracted.get("count"),
            "csv_count": csv_count,
            "status": status,
            "match_key": match_key,
            "extracted": extracted,
            "csv_record": csv_record_dict,
            "diffs": diffs,
            "pdf_preview": extracted.get("pdf_preview"),
        }

        matching_results.append(result)

    return matching_results
