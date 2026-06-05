#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase 6B-1 Region-based Extraction Tests

Purpose:
  Test precision improvement using region-based (cropped) extraction
  Instead of full-page extraction, extract from specific regions with adjusted zoom

Strategy:
  - Test 1: Basic info region (baseline - should succeed)
  - Test 2: Invoice items region (10 items - should improve)
  - Test 3: Existing support region (5 items - challenging)

Output:
  Detailed JSON results for each region
  Comparison of success rates
  Warnings and unreadable items per region
"""

import json
import base64
import sys
import os
from pathlib import Path

# Load environment variables from .env
from dotenv import load_dotenv
from pathlib import Path

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

client = Anthropic(api_key=api_key)

# Output directory for crop images
OUTPUT_DIR = Path("data/test_outputs/phase6b1_regions")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Region definitions (as percentages of page size)
# Format: (top%, bottom%, left%, right%, zoom_factor, description)
REGIONS = {
    "basic_info": {
        "bounds": (0, 20, 0, 100),  # top 20% of page (header + store/staff info)
        "zoom": 2,
        "description": "Header: store_name, staff_name, data_no, tablet_no",
        "items": ["store_name", "staff_name", "data_no", "tablet_no"],
        "prompt": """あなたは日報FAX帳票のヘッダー領域を見ています。以下の4項目を抽出してください。

【基本情報】
- store_name: 店舗名（テキスト）
- staff_name: 報告者氏名（テキスト）
- data_no: 日報データNo（英数字）
- tablet_no: タブレットNo（英数字または記号）

必ず以下のJSON形式で返してください：
{
  "store_name": "...",
  "staff_name": "...",
  "data_no": "...",
  "tablet_no": "..."
}

見つからない項目は null で返してください。
"""
    },

    "case_items": {
        "bounds": (18, 36, 5, 35),  # Left side case items section
        "zoom": 3,
        "description": "Left side case items: AU, DL, AV, DM, AY, DP, AZ, DQ, AI, CZ",
        "items": ["AU", "DL", "AV", "DM", "AY", "DP", "AZ", "DQ", "AI", "CZ"],
        "prompt": """あなたは日報FAX帳票の案件欄を見ています。以下の10項目について数値を抽出してください。

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
  - AI: 案件合計（数値）
  - CZ: 案件合計の別コード（数値）

必ず以下のJSON形式で返してください：
{
  "AU": 数値またはnull,
  "DL": 数値またはnull,
  "AV": 数値またはnull,
  "DM": 数値またはnull,
  "AY": 数値またはnull,
  "DP": 数値またはnull,
  "AZ": 数値またはnull,
  "DQ": 数値またはnull,
  "AI": 数値またはnull,
  "CZ": 数値またはnull
}

見つからない項目は 0 ではなく null で返してください。
"""
    },

    "existing_support": {
        "bounds": (18, 78, 75, 95),  # Right side existing support section
        "zoom": 4,
        "description": "Right side existing support: HH, HI, HJ, IG, IH",
        "items": ["HH", "HI", "HJ", "IG", "IH"],
        "prompt": """あなたは日報FAX帳票の既存対応欄を見ています。以下の5項目について数値を抽出してください。

【既存対応欄（一部）】
- HH: ネット追加(HT/Mz/MT)（数値）
- HI: ネット追加(auスマート)（数値）
- HJ: テレビ追加（数値）
- IG: コースアップ→5G（数値） ※独立項目
- IH: コースアップ→10G（数値） ※独立項目

重要: IG と IH は独立した項目です。合算しないでください。

必ず以下のJSON形式で返してください：
{
  "HH": 数値またはnull,
  "HI": 数値またはnull,
  "HJ": 数値またはnull,
  "IG": 数値またはnull,
  "IH": 数値またはnull
}

見つからない項目は 0 ではなく null で返してください。
""",
    },

    "new_options": {
        "bounds": (18, 50, 38, 62),  # Center new options section
        "zoom": 4,
        "description": "Center new options: GS, GT, GU, GV, GW, GX, GY, GZ, HA, HB, HC, HD, HE, HF, HG",
        "items": ["GS", "GT", "GU", "GV", "GW", "GX", "GY", "GZ", "HA", "HB", "HC", "HD", "HE", "HF", "HG"],
        "prompt": """あなたは日報FAX帳票の新規オプション等の領域を見ています。以下の15項目について数値を抽出してください。

【新規オプション等】
- GS: eo光電話（HT/MZ/MT）（数値）
- GT: eo光電話の別コード（数値）
- GU: auデジタルサービス（HT/MZ/MT）（数値）
- GV: auデジタルサービスの別コード（数値）
- GW: CS等（HT/MZ/MT）（数値）
- GX: CS等の別コード（数値）
- GY: 割引その他（HT/MZ/MT）（数値）
- GZ: 割引その他の別コード（数値）
- HA: セキュリティパック（数値）
- HB: ルーター無料（数値）
- HC: メッシュWi-Fi（数値）
- HD: 光道路 5G（HT/MZ/MT）（数値）
- HE: 光道路 10G（HT/MZ/MT）（数値）
- HF: eoLINE（数値）
- HG: eo関電前マイページ（数値）

必ず以下のJSON形式で返してください：
{
  "GS": 数値またはnull,
  "GT": 数値またはnull,
  "GU": 数値またはnull,
  "GV": 数値またはnull,
  "GW": 数値またはnull,
  "GX": 数値またはnull,
  "GY": 数値またはnull,
  "GZ": 数値またはnull,
  "HA": 数値またはnull,
  "HB": 数値またはnull,
  "HC": 数値またはnull,
  "HD": 数値またはnull,
  "HE": 数値またはnull,
  "HF": 数値またはnull,
  "HG": 数値またはnull
}

見つからない項目は 0 ではなく null で返してください。
"""
    },

    "breakdown_items": {
        "bounds": (30, 78, 5, 36),  # Left side breakdown items
        "zoom": 3,
        "description": "Left side breakdown items (products by type)",
        "items": [],  # Breakdown items have many columns, placeholder for now
        "prompt": """あなたは日報FAX帳票の内訳欄を見ています。この領域は複数製品の詳細を含んでいます。
ただし、今回は item の詳細抽出は実施しません。
見えている領域の確認のみで結構です。
"""
    }
}

# Small test regions V2 (少数項目テスト用 - bounds/prompt修正版)
# V1 → V2 変更点:
#   basic_info: (0,20,0,100) → ヘッダ(0,12) + フッタ(78,95) に分離
#   case_items_small: (18,36,5,35) → (12,20,0,45) に上方移動
#   existing_support_small: (18,50,75,95) → (12,22,58,100) に左方拡張
#   new_options_small: prompt修正 (CSV列コード→帳票上の表示名で指示)
REGIONS_SMALL = {
    "basic_info_header": {
        "bounds": (0, 14, 0, 100),  # V2: ヘッダ部分のみ（店舗名・氏名）。12→14%に拡張
        "zoom": 2,
        "description": "Header: store_name, staff_name",
        "items": ["store_name", "staff_name"],
        "prompt": """あなたは日報FAX帳票のヘッダー領域を見ています。以下の2項目を抽出してください。

【基本情報（ヘッダー）】
- store_name: 店舗名（テキスト。「小倉」「久留米」など）
- staff_name: 報告者の名前（テキスト。手書きの氏名）

必ず以下のJSON形式で返してください：
{
  "store_name": "...",
  "staff_name": "..."
}

見つからない項目は null で返してください。
"""
    },

    "basic_info_footer": {
        "bounds": (73, 95, 35, 100),  # V2: ページ下部（日報データNo, タブレットNo）。75→73%でラベル含む
        "zoom": 3,
        "description": "Footer: data_no, tablet_no",
        "items": ["data_no", "tablet_no"],
        "prompt": """あなたは日報FAX帳票のページ下部を見ています。以下の2項目を抽出してください。

【基本情報（フッター）】
- data_no: 「日報データNo.」の横に書かれた数字（8桁程度の英数字）
- tablet_no: 「タブレットNo.」の横に書かれた数字（ハイフン区切りの英数字）

必ず以下のJSON形式で返してください：
{
  "data_no": "数字またはnull",
  "tablet_no": "数字またはnull"
}

見つからない項目は null で返してください。
"""
    },

    "case_items_small": {
        "bounds": (12, 24, 0, 45),  # V2: 上方移動+下方拡張。合計行を含める。20→24%
        "zoom": 3,
        "description": "Small test: AU, AV, AY, AZ, AI (案件欄)",
        "items": ["AU", "AV", "AY", "AZ", "AI"],
        "prompt": """あなたは日報FAX帳票の【案件】欄を見ています。

この表には以下のような行があります：
- 1行目「au案件新規」→ 紹介数の数値を AU として返す
- 2行目「au案件既存」→ 紹介数の数値を AV として返す
- 5行目「その他案件新規」→ 紹介数の数値を AY として返す
- 6行目「その他案件既存」→ 紹介数の数値を AZ として返す
- 合計行 → 紹介数の合計を AI として返す

各行の「紹介」列にある手書き数字を読み取ってください。
手書きで「下」「正」等の文字がある場合はそのまま null としてください。
「—」は 0 として扱ってください。

必ず以下のJSON形式で返してください：
{
  "AU": 数値またはnull,
  "AV": 数値またはnull,
  "AY": 数値またはnull,
  "AZ": 数値またはnull,
  "AI": 数値またはnull
}

見つからない項目は 0 ではなく null で返してください。
"""
    },

    "existing_support_small": {
        "bounds": (12, 22, 58, 100),  # V2: 左方拡張。項目名を含める
        "zoom": 3,
        "description": "Small test: HH, HI, HJ (ネット追加/電話追加/テレビ追加)",
        "items": ["HH", "HI", "HJ"],
        "prompt": """あなたは日報FAX帳票の【既存対応】欄の上部を見ています。

この表には番号付きの項目が並んでいます。上から順に：
- 「1. ネット追加」の数値 → HH として返す
- 「2. 電話追加」の数値 → HI として返す
- 「3. テレビ追加」の数値 → HJ として返す

各行の右側にある手書き数字を読み取ってください。

必ず以下のJSON形式で返してください：
{
  "HH": 数値またはnull,
  "HI": 数値またはnull,
  "HJ": 数値またはnull
}

見つからない項目は 0 ではなく null で返してください。
"""
    },

    "new_options_small": {
        "bounds": (18, 50, 38, 62),  # bounds据え置き（画像は正しく写っていた）
        "zoom": 4,
        "description": "Small test: GS, GT, GU (eo光電話/地デジBS/CS)",
        "items": ["GS", "GT", "GU"],
        "prompt": """あなたは日報FAX帳票の【新規オプション等】の領域を見ています。

この表には番号付きの項目が並んでいます。上から順に：
- 「1. eo光電話」の数値 → GS として返す
- 「2. 地デジBS」の数値 → GT として返す
- 「3. CS」の数値 → GU として返す

【重要】: 各行の右側にある手書き数値を読み取ってください。

【数値「1」の認識】:
数字の「1」は、以下のようなさまざまな形で書かれています：
- アラビア数字の「1」
- 漢数字の「一」（横線）
- 縦線（|のような形）
- 「T」のような形（横棒付き縦線）
- 短い横線（チェック記号ではない、数値欄に記入された記号）

これらはすべて「1」として読み取ってください。
ただし、明らかにチェックやメモ記号（✓ や× など）ではなく、
数値欄に記入された記号であれば 1 として扱ってください。

【空欄と読み取り不可】:
- 空欄（何も記入されていない）→ null
- 読む（判読不可能な汚れや重複）→ null（warnings に理由を記載）

必ず以下のJSON形式で返してください：
{
  "GS": 数値またはnull,
  "GT": 数値またはnull,
  "GU": 数値またはnull,
  "warnings": []
}

見つからない項目は 0 ではなく null で返してください。
"""
    }
}


def extract_region_from_pdf(pdf_path: str, page_no: int, region_bounds: tuple, zoom_factor: int, region_name: str = None) -> dict:
    """
    Extract a specific region from PDF page and return as JPEG image with metadata

    Args:
        pdf_path: Path to PDF file
        page_no: Page number (0-indexed)
        region_bounds: (top%, bottom%, left%, right%) as percentages
        zoom_factor: Zoom multiplier
        region_name: Name of region for saving (e.g., "basic_info")

    Returns:
        Dict with image_bytes, metadata, and saved file path
    """
    try:
        doc = fitz.open(pdf_path)
        if page_no >= len(doc):
            raise ValueError(f"Page {page_no} not found")

        page = doc[page_no]

        # Get page dimensions
        page_rect = page.rect
        page_height = page_rect.height
        page_width = page_rect.width

        # Calculate region rectangle (in percentages)
        top_pct, bottom_pct, left_pct, right_pct = region_bounds
        region_rect = fitz.Rect(
            page_width * (left_pct / 100),
            page_height * (top_pct / 100),
            page_width * (right_pct / 100),
            page_height * (bottom_pct / 100)
        )

        # Extract region with zoom
        mat = fitz.Matrix(zoom_factor, zoom_factor)
        pix = page.get_pixmap(clip=region_rect, matrix=mat)

        # Convert to PIL Image
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        # Convert to JPEG bytes
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        image_bytes = buffer.getvalue()

        # Save to file
        saved_path = None
        if region_name:
            saved_path = OUTPUT_DIR / f"page{page_no}_{region_name}.png"
            img.save(str(saved_path), format="PNG")

        doc.close()

        # Return dict with metadata
        return {
            "image_bytes": image_bytes,
            "pixel_width": pix.width,
            "pixel_height": pix.height,
            "image_size_kb": len(image_bytes) / 1024,
            "saved_path": str(saved_path),
            "bounds": region_bounds,
            "zoom": zoom_factor,
            "region_name": region_name
        }

    except Exception as e:
        print(f"ERROR: Failed to extract PDF region: {e}")
        raise


def is_retryable_error(exception: Exception) -> bool:
    """Determine if an error is retryable"""
    error_msg = str(exception).lower()

    # Retryable errors
    retryable_keywords = [
        "connection", "timeout", "temporary", "unavailable",
        "rate_limit", "429", "overload", "temporarily"
    ]

    if any(keyword in error_msg for keyword in retryable_keywords):
        return True

    # Non-retryable errors (authentication, invalid model, malformed request)
    non_retryable_keywords = [
        "authentication", "unauthorized", "401", "invalid api key",
        "model not found", "invalid_request_error", "invalid model"
    ]

    if any(keyword in error_msg for keyword in non_retryable_keywords):
        return False

    # Default: retryable (assume network issues)
    return True


def extract_with_vision_api(image_bytes: bytes, prompt: str, region_name: str = None, image_width: int = None, image_height: int = None) -> dict:
    """Extract details using Vision API and save raw response"""

    model_name = "claude-sonnet-4-6"

    try:
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        image_size_kb = len(image_bytes) / 1024

        message = client.messages.create(
            model=model_name,
            max_tokens=512,
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
                            "text": prompt
                        }
                    ],
                }
            ],
        )

        response_text = message.content[0].text

        # Save raw response
        if region_name:
            raw_file = OUTPUT_DIR / f"raw_{region_name}.txt"
            with open(raw_file, 'w', encoding='utf-8') as f:
                f.write(response_text)

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
            if region_name:
                print(f"[{region_name}] JSON parse error: {e}")
                print(f"  Raw response (first 500 chars):")
                print(f"  {response_text[:500]}")
                print(f"  Saved to: {OUTPUT_DIR / f'raw_{region_name}.txt'}")
            else:
                print(f"JSON parse error: {e}")
            return {}

    except Exception as e:
        # Detailed error logging
        exception_type = type(e).__name__
        exception_msg = str(e)
        retryable = is_retryable_error(e)

        print(f"\nERROR: Vision API call failed")
        print(f"  Exception type: {exception_type}")
        print(f"  Message: {exception_msg}")

        if region_name:
            print(f"  Region: {region_name}")
        print(f"  Model: {model_name}")

        if image_width and image_height:
            print(f"  Image dimensions: {image_width}x{image_height} px")
        if image_size_kb:
            print(f"  Image size: {image_size_kb:.1f} KB")

        print(f"  Retryable: {'YES' if retryable else 'NO'}")
        print()

        return {}


def test_api_connectivity() -> bool:
    """Test basic API connectivity with text-only message"""

    model_name = "claude-sonnet-4-6"

    try:
        print("[API Connectivity Test] Sending text-only message...")

        message = client.messages.create(
            model=model_name,
            max_tokens=10,
            messages=[
                {
                    "role": "user",
                    "content": "Reply OK only."
                }
            ],
        )

        response_text = message.content[0].text
        print(f"[API Connectivity Test] SUCCESS: API responded with: {response_text}")
        return True

    except Exception as e:
        exception_type = type(e).__name__
        exception_msg = str(e)
        retryable = is_retryable_error(e)

        print(f"[API Connectivity Test] FAILED")
        print(f"  Exception type: {exception_type}")
        print(f"  Message: {exception_msg}")
        print(f"  Model: {model_name}")
        print(f"  Retryable: {'YES' if retryable else 'NO'}")
        print()

        return False


def analyze_results(region_name: str, expected_items: list, extracted_data: dict, expected_values: dict = None) -> dict:
    """Analyze extraction results with optional expected value validation

    Args:
        region_name: Name of region being tested
        expected_items: List of item codes to extract
        extracted_data: Dict of extracted values
        expected_values: Dict mapping item codes to expected values or status
                        Values can be: actual value, None (for null), or string status like "blank", "unreadable"

    Returns:
        Analysis dict with success counts based on evaluation criteria
    """

    success_count = 0
    null_count = 0
    unreadable_items = []
    warnings = []
    item_results = []

    for item in expected_items:
        value = extracted_data.get(item)
        expected = expected_values.get(item) if expected_values else None

        # Determine if value is null
        is_null = value is None or value == ""

        # Evaluate based on expected value
        if expected_values and item in expected_values:
            expected_status = expected_values[item]

            # Expected blank/empty → null is success
            if expected_status == "blank" and is_null:
                success_count += 1
                item_results.append({
                    "item": item,
                    "expected": "blank",
                    "actual": "null",
                    "result": "[OK] success"
                })
            # Expected unreadable → null is acceptable
            elif expected_status == "unreadable" and is_null:
                success_count += 1
                item_results.append({
                    "item": item,
                    "expected": "unreadable",
                    "actual": "null",
                    "result": "[OK] acceptable"
                })
            # Expected value → must extract correctly
            elif isinstance(expected_status, (int, float, str)) and expected_status != "blank" and expected_status != "unreadable":
                if value == expected_status:
                    success_count += 1
                    item_results.append({
                        "item": item,
                        "expected": expected_status,
                        "actual": value,
                        "result": "[OK] success"
                    })
                elif is_null:
                    unreadable_items.append(item)
                    item_results.append({
                        "item": item,
                        "expected": expected_status,
                        "actual": "null",
                        "result": "[NG] failed (expected value)"
                    })
                else:
                    item_results.append({
                        "item": item,
                        "expected": expected_status,
                        "actual": value,
                        "result": "[NG] mismatch"
                    })
            else:
                # No specific expectation
                if is_null:
                    null_count += 1
                    unreadable_items.append(item)
                else:
                    success_count += 1
        else:
            # No expected value provided — use original logic
            if is_null:
                null_count += 1
                unreadable_items.append(item)
            else:
                success_count += 1

    success_rate = success_count / len(expected_items) if expected_items else 0

    return {
        "region": region_name,
        "expected_items": len(expected_items),
        "success_count": success_count,
        "null_count": null_count,
        "success_rate": success_rate,
        "unreadable_items": unreadable_items,
        "warnings": warnings,
        "extracted_data": extracted_data,
        "item_results": item_results if expected_values else []
    }


def test_phase6b1_regions(mode: str = "full"):
    """Test Phase 6B-1: region-based extraction"""

    print("=" * 80)
    print("Phase 6B-1 Region-based Extraction Test")
    print("=" * 80)

    pdf_path = "tests/fixtures/geo_pdf_reconciliation/20260529130020168.pdf"
    model_name = "claude-sonnet-4-6"

    # Test multiple pages: page 0, 3, 7 for new_options validation
    test_pages = [0, 3, 7]

    # Define expected values for both pages
    page_expected_values = {
        0: {
            "new_options_small": {
                "GS": 1,            # eo光電話: 漢数字「一」
                "GT": None,         # 地デジBS: 空欄
                "GU": 1             # CS: 漢数字「一」
            },
            "case_items_small": {
                "AU": "unreadable",  # Handwritten "下" character
                "AV": 0,             # Dash "—" interpreted as 0
                "AY": "blank",       # Not visible
                "AZ": "blank",       # Not visible
                "AI": 5              # Handwritten number 5
            }
        },
        3: {
            # Page 3: Based on visual inspection, has values in new_options area
            "new_options_small": {
                "GS": 1,            # eo光電話: 「T」のような手書き = 1（推定）
                "GT": 1,            # 地デジBS: 「T」のような手書き = 1（推定）
                "GU": 1             # CS: 「一」のような手書き = 1
            }
        },
        7: {
            # Page 7: Based on visual inspection, has limited values in new_options area
            "new_options_small": {
                "GS": None,         # eo光電話: 空欄に見える
                "GT": None,         # 地デジBS: 空欄
                "GU": None          # CS: 空欄
            }
        }
    }

    # Display preflight information
    print("\n[Preflight Check]")

    api_key_exists = bool(os.getenv("ANTHROPIC_API_KEY"))
    print(f"  API key loaded: {'YES' if api_key_exists else 'NO'}")
    print(f"  Model name: {model_name}")

    pdf_exists = Path(pdf_path).exists()
    print(f"  PDF file exists: {'YES' if pdf_exists else 'NO'} ({pdf_path})")

    num_regions = len(REGIONS)
    print(f"  Number of regions: {num_regions}")

    print(f"  Mode: {mode}")
    print(f"  Test pages: {test_pages}")

    # Check file
    print(f"\n[Step 1] Checking PDF file")
    if not pdf_exists:
        print(f"ERROR: PDF file not found: {pdf_path}")
        return False

    print(f"OK: {pdf_path}")

    # Step 2: Test API connectivity
    print(f"\n[Step 2] Testing API connectivity (text-only message)")
    connectivity_ok = test_api_connectivity()

    if not connectivity_ok:
        print("WARNING: API connectivity test failed. Proceeding with region tests anyway.")
        print()

    print(f"\n[Step 3] Running region-based extraction tests")

    # Run tests for each page and region
    all_results = {}

    for page_no in test_pages:
        print(f"\n[Page {page_no}] Testing regions on page {page_no}")
        print("=" * 80)

        for region_key, region_config in REGIONS.items():
                print(f"\n  [Test] Region: {region_key}")
                print(f"    Description: {region_config['description']}")
                print(f"    Bounds: {region_config['bounds']}")
                print(f"    Zoom: {region_config['zoom']}x")
                print(f"    Items: {len(region_config['items'])}")

                try:
                    # Extract region
                    region_data = extract_region_from_pdf(
                        pdf_path,
                        page_no,
                        region_config['bounds'],
                        region_config['zoom'],
                        region_name=f"page{page_no}_{region_key}"
                    )
                    image_bytes = region_data['image_bytes']

                    # Log region metadata
                    print(f"    Image extracted: {region_data['image_size_kb']:.1f} KB")
                    print(f"    Pixel dimensions: {region_data['pixel_width']}x{region_data['pixel_height']}")
                    print(f"    Saved to: {region_data['saved_path']}")

                    # Call Vision API (with region_name for raw response saving)
                    extracted = extract_with_vision_api(
                        image_bytes,
                        region_config['prompt'],
                        region_name=f"page{page_no}_{region_key}",
                        image_width=region_data['pixel_width'],
                        image_height=region_data['pixel_height']
                    )

                    # Analyze with expected values if available
                    region_expected = page_expected_values.get(page_no, {}).get(region_key) if page_no in page_expected_values else None
                    analysis = analyze_results(
                        region_key,
                        region_config['items'],
                        extracted,
                        expected_values=region_expected
                    )

                    result_key = f"page{page_no}_{region_key}"
                    all_results[result_key] = {
                        "page": page_no,
                        "region": region_key,
                        "config": region_config,
                        "analysis": analysis,
                        "region_metadata": {
                            "bounds": region_data['bounds'],
                            "zoom": region_data['zoom'],
                            "image_size_kb": region_data['image_size_kb'],
                            "pixel_width": region_data['pixel_width'],
                            "pixel_height": region_data['pixel_height'],
                            "saved_path": region_data['saved_path']
                        }
                    }

                    # Display results
                    print(f"    Success rate: {analysis['success_rate'] * 100:.1f}% ({analysis['success_count']}/{analysis['expected_items']})")
                    print(f"    Unreadable: {analysis['null_count']} items")
                    if analysis['unreadable_items']:
                        print(f"      Items: {', '.join(analysis['unreadable_items'][:5])}")

                    # Display detailed item results if expected values were used
                    if analysis.get('item_results'):
                        print(f"    Item-by-item evaluation:")
                        for item_result in analysis['item_results']:
                            result_str = item_result['result'].replace('✓', '[OK]').replace('✗', '[NG]')
                            print(f"      {item_result['item']}: expected={item_result['expected']}, actual={item_result['actual']} -> {result_str}")

                    if analysis['warnings']:
                        print(f"    Warnings: {analysis['warnings']}")

                except Exception as e:
                    print(f"    ERROR: {e}")
                    result_key = f"page{page_no}_{region_key}"
                    all_results[result_key] = {"error": str(e)}

    # Summary
    print(f"\n" + "=" * 80)
    print("Summary")
    print("=" * 80)

    for region_key, result in all_results.items():
        if "error" in result:
            print(f"\n{region_key}: ERROR - {result['error']}")
        else:
            analysis = result['analysis']
            metadata = result.get('region_metadata', {})
            print(f"\n{region_key}:")
            print(f"  Bounds: {metadata.get('bounds')}")
            print(f"  Zoom: {metadata.get('zoom')}x")
            print(f"  Image size: {metadata.get('image_size_kb'):.1f} KB")
            print(f"  Pixel dimensions: {metadata.get('pixel_width')}x{metadata.get('pixel_height')}")
            print(f"  Saved: {metadata.get('saved_path')}")
            print(f"  Success rate: {analysis['success_rate'] * 100:.1f}%")
            print(f"  Success: {analysis['success_count']}/{analysis['expected_items']}")

    # Save results
    output_file = Path("temp_phase6b1_results.json")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)

    print(f"\nOK: Results saved to {output_file}")

    print("\n" + "=" * 80)
    print("Phase 6B-1 Region-based Test Complete")
    print("=" * 80)

    return True


def test_phase6b1_small():
    """Test Phase 6B-1 with small number of items"""
    # Run test with REGIONS_SMALL instead of REGIONS
    original_regions = globals()['REGIONS']
    globals()['REGIONS'] = REGIONS_SMALL

    success = test_phase6b1_regions(mode="small")

    globals()['REGIONS'] = original_regions
    return success


if __name__ == "__main__":
    import sys

    # Check if small test is requested
    if len(sys.argv) > 1 and sys.argv[1] == "small":
        print("Running small-item test mode")
        success = test_phase6b1_small()
    else:
        success = test_phase6b1_regions()

    sys.exit(0 if success else 1)
