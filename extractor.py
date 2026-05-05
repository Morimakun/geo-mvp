"""Claude Vision API を使用した帳票項目抽出モジュール"""

import json
import os
from typing import Optional
import base64
from anthropic import Anthropic

# Claude API クライアント初期化
client = Anthropic()

EXTRACTION_PROMPT = """以下の帳票画像から、以下の6つの項目を抽出し、JSON形式で返してください。

抽出対象項目：
1. 処理日（日付、フォーマット：YYYY-MM-DD）
2. 店舗名（文字列）
3. 担当者名（文字列）
4. 件数（数値）
5. 合計値（数値）
6. 備考（文字列、省略可）

回答フォーマット：
{
  "処理日": "YYYY-MM-DD",
  "店舗名": "店舗名",
  "担当者名": "担当者名",
  "件数": 0,
  "合計値": 0,
  "備考": "備考"
}

注意：
- 項目が見つからない場合は null を使用してください
- 数値は整数または小数で返してください
- 日付が曖昧な場合は null を返してください
- 必ずJSON形式のみを返してください（説明文は不要）"""


def extract_items_from_image(image_base64: str) -> dict:
    """
    画像から帳票項目を抽出する

    Args:
        image_base64: base64エンコードされた画像データ

    Returns:
        抽出結果を含む辞書
    """
    try:
        # Claude Vision API を呼び出し
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
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
            # JSONブロックを抽出（```json ... ``` の形式に対応）
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text.strip()

            result = json.loads(json_str)
        except (json.JSONDecodeError, IndexError):
            # JSON解析失敗時
            result = {
                "処理日": None,
                "店舗名": None,
                "担当者名": None,
                "件数": None,
                "合計値": None,
                "備考": None,
                "error": "Failed to parse JSON response"
            }

        return result

    except Exception as e:
        return {
            "処理日": None,
            "店舗名": None,
            "担当者名": None,
            "件数": None,
            "合計値": None,
            "備考": None,
            "error": str(e)
        }


def validate_extraction_result(data: dict) -> dict:
    """
    抽出結果を検証し、型を正規化する

    Args:
        data: 抽出結果

    Returns:
        正規化されたデータ
    """
    validated = {}

    # 文字列フィールド
    for field in ["処理日", "店舗名", "担当者名", "備考"]:
        validated[field] = data.get(field)
        if validated[field] is not None:
            validated[field] = str(validated[field]).strip()

    # 数値フィールド
    for field in ["件数", "合計値"]:
        try:
            value = data.get(field)
            if value is not None:
                validated[field] = int(float(value))
            else:
                validated[field] = None
        except (ValueError, TypeError):
            validated[field] = None

    return validated
