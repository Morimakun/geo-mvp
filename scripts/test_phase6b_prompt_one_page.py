#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 6B-0 Prompt Test: Small-scale PDF detail extraction verification

Purpose:
  Test whether Claude Vision API can extract detailed numeric values from PDF
  Target: 1 page, 15 items (not full 183)

Output format:
  JSON with page_no, store_name, staff_name, data_no, tablet_no, right_side_data, warnings, unreadable_items
"""

import json
import base64
import sys
import os
from pathlib import Path

# Load environment variables from .env
from dotenv import load_dotenv

# Load from project root
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

# Check API key
api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
if not api_key:
    raise RuntimeError(
        "ANTHROPIC_API_KEY が未設定です。\n"
        "以下のいずれかで設定してください：\n"
        "1. プロジェクトルートの .env ファイルに ANTHROPIC_API_KEY=sk-ant-... を追加\n"
        "2. PowerShell で $env:ANTHROPIC_API_KEY = '...' を実行\n"
    )

import fitz  # PyMuPDF
from PIL import Image
from anthropic import Anthropic
from io import BytesIO

# Initialize Anthropic client with explicit API key
client = Anthropic(api_key=api_key)

# Phase 6B-0: Vision Prompt for 15 items test
VISION_PROMPT_PHASE6B0 = """
あなたは日報FAX帳票のPDF画像を見ています。以下の15項目について、PDF上から数値を抽出してください。

【抽出対象項目】

【基本情報】
- store_name: 店舗名（テキスト）
- staff_name: 報告者氏名（テキスト）
- data_no: 日報データNo（英数字）
- tablet_no: タブレットNo（英数字または記号）

【案件欄】
au案件新規（複数コード対応）:
  - AU: au案件新規紹介数（数値）
  - DL: au案件新規紹介数の別コード（数値）
au案件既存（複数コード対応）:
  - AV: au案件既存紹介数（数値）
  - DM: au案件既存紹介数の別コード（数値）
その他案件新規（複数コード対応）:
  - AY: その他案件新規紹介数（数値）
  - DP: その他案件新規紹介数の別コード（数値）
その他案件既存（複数コード対応）:
  - AZ: その他案件既存紹介数（数値）
  - DQ: その他案件既存紹介数の別コード（数値）
案件合計（複数コード対応）:
  - AI: 案件合計（数字で記入）（数値）
  - CZ: 案件合計の別コード（数値）

【既存対応欄（一部）】
- HH: ネット追加(HT/Mz/MT)（数値）
- HI: ネット追加(auスマート)（数値）
- HJ: テレビ追加（数値）
- IG: コースアップ→5G（数値） ※ item 28 ではなく独立項目
- IH: コースアップ→10G（数値） ※ item 28 ではなく独立項目

【回答形式】
必ず以下のJSON形式で返してください。見つからない項目は null を返してください。0 ではなく null です。

{
  "page_no": 1,
  "store_name": "店舗名またはnull",
  "staff_name": "氏名またはnull",
  "data_no": "日報NoまたはDataNoまたはnull",
  "tablet_no": "タブレットNoまたはnull",
  "right_side_data": {
    "AU": 数値またはnull,
    "DL": 数値またはnull,
    "AV": 数値またはnull,
    "DM": 数値またはnull,
    "AY": 数値またはnull,
    "DP": 数値またはnull,
    "AZ": 数値またはnull,
    "DQ": 数値またはnull,
    "AI": 数値またはnull,
    "CZ": 数値またはnull,
    "HH": 数値またはnull,
    "HI": 数値またはnull,
    "HJ": 数値またはnull,
    "IG": 数値またはnull,
    "IH": 数値またはnull
  },
  "warnings": [],
  "unreadable_items": []
}

【重要な注意事項】
- 読めない項目は 0 ではなく null で返してください
- item 28（コースアップ→5G→10G の合算）は未使用のため、IG と IH は別々に返してください。合算しないでください
- AU と DL は異なるセルかもしれませんが、もし同じセルなら同じ値を入れてください
- 複数コード対応の項目（AU/DL、AV/DM等）は両方とも見つけるようにしてください
- 手書き値の読取が不鮮明な場合は null を入れてください
- 必ず JSON 形式のみで回答してください（マークダウン記号不要）
- warnings 配列には読取困難だった箇所の説明を入れてください
- unreadable_items 配列には null になった項目名を入れてください
"""

def extract_pdf_page_to_image(pdf_path: str, page_no: int = 0) -> bytes:
    """
    Extract a PDF page to image (JPEG)

    Args:
        pdf_path: Path to PDF file
        page_no: Page number (0-indexed)

    Returns:
        JPEG image bytes
    """
    try:
        doc = fitz.open(pdf_path)
        if page_no >= len(doc):
            raise ValueError(f"Page {page_no} not found (total {len(doc)} pages)")

        page = doc[page_no]

        # Zoom 2x for better quality
        mat = fitz.Matrix(2, 2)
        pix = page.get_pixmap(matrix=mat)

        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Convert to JPEG bytes
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)

        doc.close()

        return buffer.getvalue()

    except Exception as e:
        print(f"ERROR: Failed to extract PDF page: {e}")
        raise

def extract_with_vision_api(image_bytes: bytes) -> dict:
    """
    Extract details from PDF page image using Claude Vision API

    Args:
        image_bytes: JPEG image bytes

    Returns:
        Extraction result dictionary
    """
    try:
        # Encode image to base64
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")

        print("Calling Claude Vision API...")

        message = client.messages.create(
            model="claude-sonnet-4-6",
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
                            "text": VISION_PROMPT_PHASE6B0
                        }
                    ],
                }
            ],
        )

        # Parse response
        response_text = message.content[0].text

        print(f"API Response (first 500 chars):\n{response_text[:500]}\n")

        # Extract JSON
        try:
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text.strip()

            result = json.loads(json_str)
            return result

        except (json.JSONDecodeError, IndexError, ValueError) as e:
            print(f"JSON parse error: {e}")
            print(f"Response text:\n{response_text}")
            return {
                "page_no": 0,
                "store_name": None,
                "staff_name": None,
                "data_no": None,
                "tablet_no": None,
                "right_side_data": {k: None for k in ["AU", "DL", "AV", "DM", "AY", "DP", "AZ", "DQ", "AI", "CZ", "HH", "HI", "HJ", "IG", "IH"]},
                "warnings": [f"JSON parsing failed: {str(e)}"],
                "unreadable_items": []
            }

    except Exception as e:
        print(f"ERROR: Vision API call failed: {e}")
        return {
            "page_no": 0,
            "store_name": None,
            "staff_name": None,
            "data_no": None,
            "tablet_no": None,
            "right_side_data": {k: None for k in ["AU", "DL", "AV", "DM", "AY", "DP", "AZ", "DQ", "AI", "CZ", "HH", "HI", "HJ", "IG", "IH"]},
            "warnings": [f"Vision API call failed: {str(e)}"],
            "unreadable_items": []
        }

def test_phase6b_prompt():
    """Test Phase 6B prompt on real PDF"""

    print("=" * 80)
    print("Phase 6B-0 Prompt Test: Single Page Detail Extraction")
    print("=" * 80)

    # Target PDF
    pdf_path = "tests/fixtures/geo_pdf_reconciliation/20260529130020168.pdf"
    page_no = 0  # First page

    # Step 1: Check file existence
    print(f"\n[Step 1] Checking PDF file")
    if not Path(pdf_path).exists():
        print(f"ERROR: PDF file not found: {pdf_path}")
        return False
    print(f"OK: {pdf_path} found (size: {Path(pdf_path).stat().st_size / 1024:.1f} KB)")

    # Step 2: Extract page to image
    print(f"\n[Step 2] Extracting page {page_no} to image")
    try:
        image_bytes = extract_pdf_page_to_image(pdf_path, page_no)
        print(f"OK: Page extracted ({len(image_bytes) / 1024:.1f} KB)")
    except Exception as e:
        print(f"FAIL: {e}")
        return False

    # Step 3: Call Vision API
    print(f"\n[Step 3] Calling Claude Vision API")
    result = extract_with_vision_api(image_bytes)

    # Step 4: Analyze result
    print(f"\n[Step 4] Analyzing extraction result")

    extracted_items = 0
    null_items = 0

    right_side = result.get("right_side_data", {})
    for key, value in right_side.items():
        if value is not None and value != "":
            extracted_items += 1
        else:
            null_items += 1

    print(f"  Extracted items: {extracted_items}/15")
    print(f"  Null items: {null_items}/15")
    print(f"  Store name: {result.get('store_name')}")
    print(f"  Staff name: {result.get('staff_name')}")
    print(f"  Data No: {result.get('data_no')}")
    print(f"  Tablet No: {result.get('tablet_no')}")

    if result.get("warnings"):
        print(f"  Warnings: {len(result['warnings'])} items")
        for warning in result.get("warnings", []):
            print(f"    - {warning}")

    if result.get("unreadable_items"):
        print(f"  Unreadable items: {result['unreadable_items']}")

    # Step 5: Display JSON
    print(f"\n[Step 5] Extraction Result JSON")
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Step 6: Save result
    print(f"\n[Step 6] Saving result")
    result_file = Path("temp_phase6b_result.json")
    with open(result_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"OK: Saved to {result_file}")

    print("\n" + "=" * 80)
    print("Phase 6B-0 Prompt Test Complete")
    print("=" * 80)

    return True

if __name__ == "__main__":
    success = test_phase6b_prompt()
    sys.exit(0 if success else 1)
