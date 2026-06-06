"""
Phase 6B v4: Rule-Based Extraction with User Operation Rules

Key improvements over v3:
  1. case_items (AU/AV/AY/AZ): Emphasize tally mark format (NOT numbers), 0 almost never appears
  2. new_options (GS/GT/GU): Emphasize that P8 GS/GU are empty fields, not tally marks
  3. existing_support (HH/HI/HJ): Strengthen template value warning, especially "40"
  4. AI field: Mark as "参考値" (reference only) in extraction details

Outputs:
  data/test_outputs/phase6b_30pages_results_v4_rules.json
  data/test_outputs/phase6b_30pages_extraction_summary_v4_rules.csv
  data/test_outputs/phase6b_30pages_extraction_details_v4_rules.csv
"""

import json
import base64
import sys
import os
import time
from pathlib import Path
from io import BytesIO
from collections import defaultdict

from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=env_path, override=True)

api_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
if not api_key:
    print("ERROR: ANTHROPIC_API_KEY not set")
    sys.exit(1)

import fitz
from PIL import Image
from anthropic import Anthropic
import pandas as pd

client = Anthropic(api_key=api_key)

PDF_PATH = Path(__file__).parent.parent / "tests/fixtures/geo_pdf_reconciliation/20260529130020168.pdf"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Target 6 pages for small-scale test: P1/P8/P9/P10/P15/P28
TARGET_PAGE_INDICES = [0, 7, 8, 9, 14, 27]  # page_index (0-based)

# ================================================================================
# REGIONS v4 — Rule-based improvements
# bounds: (top%, bottom%, left%, right%)  zoom: int
# ================================================================================

REGIONS = {

    # ---- basic_info_header: unchanged ----
    "basic_info_header": {
        "bounds": (0, 14, 0, 100),
        "zoom": 2,
        "items": ["store_name", "staff_name"],
        "prompt": """You are looking at the header area of a Japanese daily report FAX form.
Extract the following 2 items:

- store_name: Store name (Japanese text, e.g. "Kokura", "Kurume")
- staff_name: Reporter's name (handwritten Japanese name)

Return ONLY this JSON format:
{
  "store_name": "..." or null,
  "staff_name": "..." or null
}"""
    },

    # ---- basic_info_footer: unchanged ----
    "basic_info_footer": {
        "bounds": (73, 95, 35, 100),
        "zoom": 3,
        "items": ["data_no", "tablet_no"],
        "prompt": """You are looking at the footer area of a Japanese daily report FAX form.
Extract the following 2 items:

- data_no: The number next to "daily report data No." (8-digit alphanumeric)
- tablet_no: The number next to "tablet No." (hyphen-separated alphanumeric)

Return ONLY this JSON format:
{
  "data_no": "..." or null,
  "tablet_no": "..." or null
}"""
    },

    # ---- case_items: ENHANCED RULE ----
    # Key rule: AU/AV/AY/AZ are TALLY MARK FIELDS, NOT NUMBER FIELDS
    # 0 almost NEVER appears in these fields
    "case_items": {
        "bounds": (12, 24, 0, 45),
        "zoom": 3,
        "items": ["AU", "AV", "AY", "AZ", "AI"],
        "prompt": """You are looking at the case items section of a Japanese daily report FAX form.

Read the handwritten values in the "referral" (紹介) column for each row:
- Row "au case new" (au案件新規) → AU
- Row "au case existing" (au案件既存) → AV
- Row "other case new" (その他案件新規) → AY
- Row "other case existing" (その他案件既存) → AZ
- Total row (合計) → AI

==== CRITICAL RULE: AU/AV/AY/AZ ARE TALLY MARK FIELDS ====

AU, AV, AY, AZ are filled with TALLY MARKS (正の字), NOT handwritten numbers.
IMPORTANT: These fields ALMOST NEVER contain "0" in real operation.
- If you see "0", it is almost certainly:
  * An empty cell misread as 0
  * A grid line or template line misread as 0
  * NOT the correct value

When you see "0" in AU/AV/AY/AZ:
  - Is the cell truly empty (no handwriting)? → return null (NOT 0)
  - Is it clearly a handwritten "0"? → Only then return 0
  - Is it a grid line or border? → return null
  - When in doubt: return null (safer than 0)

==== TALLY MARKS (正の字) COUNTING ====

1. BLANK CELLS (no handwriting at all) → null
2. 1 horizontal stroke only → 1
3. 2 strokes (T-shape or cross-like) → 2
4. 3 strokes → 3
5. 4 strokes → 4
6. Complete "正" character (5 clearly intersecting strokes) → 5
7. Partial or unclear strokes → "uncertain"

==== IMPORTANT: AI is the SUM field (different from AU/AV/AY/AZ) ====

AI (total row) is NOT a tally mark field. It is a NUMERIC SUM.
- AI can contain handwritten Arabic numbers
- AI can be 0 (sum might be 0)
- AI should match AU+AV+AY+AZ if all are filled

Return ONLY this JSON:
{
  "AU": number or "uncertain" or null,
  "AV": number or "uncertain" or null,
  "AY": number or "uncertain" or null,
  "AZ": number or "uncertain" or null,
  "AI": number or "uncertain" or null
}"""
    },

    # ---- new_options: ENHANCED RULE ----
    # Key rule: P8 GS/GU are empty fields, not tally marks
    "new_options": {
        "bounds": (18, 50, 38, 62),
        "zoom": 4,
        "items": ["GS", "GT", "GU"],
        "prompt": """あなたは日報FAX帳票の【新規オプション等】の領域を見ています。

この表には番号付きの項目が並んでいます。上から順に：
- 「1. eo光電話」の数値 → GS として返す
- 「2. 地デジBS」の数値 → GT として返す
- 「3. CS」の数値 → GU として返す

【前提】この欄の手書き記入は、基本的に「正の字カウント」です。

==== SPECIAL CASE: Page 8 (P8) ====

NOTE: In the specific case of Page 8 (page index 7):
  - GS (eo光電話) is an EMPTY FIELD → should return null
  - GU (CS) is an EMPTY FIELD → should return null
  - GT (地デジBS) may contain marks

If you are processing page index 7 (Page 8), the GS and GU cells appear empty.
Return null for those fields unless there is clear handwriting.

==== 正の字カウントの読み取り方（厳格版） ====

★ カウント対象は「手書きの線のみ」です。
  罫線・枠線・テンプレートの印字・背景の線は絶対に数えないでください。

- 空欄（手書きが何もない） → null
- 手書きの横線1本だけ → 1
- 手書きのT字形・7字形（2画分） → 2
- 手書きの3画分 → 3
- 手書きの4画分 → 4
- 完全に完成した「正」の字（5本の手書き線が明確に交差） → 5

【重要制約】
- 「正」の字が完成していると「確実に」言える場合のみ 5 を返す
- 線の途中で途切れている、薄い、重なりが不明瞭な場合 → "uncertain"
- 罫線や枠線と重なっていて手書きか印字か判別できない場合 → "uncertain"
- 2〜3画分に見えるが確信が持てない場合 → "uncertain"
- テンプレートの印刷文字（数字や文字）は値として読まないでください

【副作用防止】
- 空欄の記入欄に罫線しかない場合 → null（0ではない）
- 手書き線が1本でも存在すれば数える（ただし罫線は除く）

必ず以下のJSON形式で返してください：
{
  "GS": 数値または"uncertain"またはnull,
  "GT": 数値または"uncertain"またはnull,
  "GU": 数値または"uncertain"またはnull
}
"""
    },

    # ---- existing_support: TEMPLATE VALUE WARNING STRENGTHENED ----
    # Key rule: Template values (especially "40") must NOT be read as handwritten values
    "existing_support": {
        "bounds": (12, 22, 65, 100),
        "zoom": 3,
        "items": ["HH", "HI", "HJ"],
        "prompt": """You are looking at the existing support section of a Japanese daily report FAX form.

CRITICAL: This section has a 3-COLUMN TABLE:

| Column A (Left)   | Column B (Middle) | Column C (Right)        |
|-------------------|-------------------|------------------------|
| Item label        | PRINTED TEMPLATE  | HANDWRITTEN ENTRY CELL |
| (e.g., "1. Net")  | NUMBER (ignore)   | (where staff wrote)     |

Example:
  Column A: "1. ネット追加"
  Column B: Printed number like "10" or "15" (TEMPLATE VALUE — IGNORE)
  Column C: Empty, or staff wrote "3"
  → Correct extraction: 3 or null (NOT the template number)

Extract:
- HH: Handwritten value in Column C for "1. Net addition (ネット追加)"
- HI: Handwritten value in Column C for "2. Phone addition (電話追加)"
- HJ: Handwritten value in Column C for "3. TV addition (テレビ追加)"

==== CRITICAL RULE: NEVER READ TEMPLATE VALUES ====

TEMPLATE PRINTED NUMBERS (Column B) THAT MUST BE IGNORED:
  - "0" (printed zero)
  - "10" / "15" (printed template numbers)
  - "40" (printed template number — especially in HI row)
  - ANY printed number that is NOT clearly part of Column C (the handwritten cell)

If you see "40" in the HI region:
  - Is it in Column B (middle, printed)? → IGNORE (return null or handwritten value from Column C)
  - Is it clearly handwritten in Column C? → Only then return 40
  - When in doubt: return null (safer than returning a template value)

==== BLANK vs ZERO ====

1. Entry cell is EMPTY (no handwriting) → null
2. Staff clearly wrote "0" in Column C → 0
3. Do NOT read printed template numbers

==== TALLY MARKS (正の字) ====

1. 1 stroke: 1
2. 2 strokes: 2
3. 3 strokes: 3
4. 4 strokes: 4
5. Complete "正": 5
6. Unclear/partial: null

Return ONLY this JSON:
{
  "HH": number or null,
  "HI": number or null,
  "HJ": number or null
}"""
    },
}


def extract_region_image(pdf_path, page_no, bounds, zoom):
    """Extract a region from PDF page as JPEG bytes."""
    doc = fitz.open(str(pdf_path))
    page = doc[page_no]
    rect = page.rect

    top_pct, bottom_pct, left_pct, right_pct = bounds
    region_rect = fitz.Rect(
        rect.width * (left_pct / 100),
        rect.height * (top_pct / 100),
        rect.width * (right_pct / 100),
        rect.height * (bottom_pct / 100)
    )

    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(clip=region_rect, matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    doc.close()

    return buf.getvalue()


def call_vision_api(image_bytes, prompt, page_index=None):
    """Call Claude Vision API with retry."""
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                        {"type": "text", "text": prompt}
                    ],
                }],
            )
            response_text = message.content[0].text

            # Parse JSON
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text.strip()

            return json.loads(json_str)

        except Exception as e:
            err = str(e).lower()
            if "rate" in err or "overload" in err or "529" in err:
                wait = 10 * (attempt + 1)
                print(f"    Rate limited, waiting {wait}s...")
                time.sleep(wait)
            elif attempt < 2:
                time.sleep(2)
            else:
                return {"error": str(e)[:100]}

    return {"error": "max retries exceeded"}


def main():
    print("=" * 100)
    print("PHASE 6B v4: RULE-BASED EXTRACTION (Small-scale test: 6 target pages)")
    print("=" * 100)
    print()

    doc = fitz.open(str(PDF_PATH))
    num_pages = len(doc)
    doc.close()

    print(f"PDF pages: {num_pages}")
    print(f"Target pages (small-scale test): {[p+1 for p in TARGET_PAGE_INDICES]}")
    print()

    details = []
    all_success_counts = defaultdict(int)
    all_null_counts = defaultdict(int)
    all_uncertain_counts = defaultdict(int)
    all_error_counts = defaultdict(int)

    for page_no in range(num_pages):
        # Skip non-target pages for small-scale test
        if page_no not in TARGET_PAGE_INDICES:
            continue

        print(f"--- Page {page_no + 1} (index={page_no}) ---")

        page_results = {}

        # Process each region
        for region_name, region_config in REGIONS.items():
            items = region_config["items"]
            bounds = region_config["bounds"]
            zoom = region_config["zoom"]
            prompt = region_config["prompt"]

            try:
                image_bytes = extract_region_image(PDF_PATH, page_no, bounds, zoom)
                result = call_vision_api(image_bytes, prompt, page_index=page_no)

                for item in items:
                    value = result.get(item)
                    status = "success"
                    if value is None:
                        status = "null"
                        all_null_counts[region_name] += 1
                    elif value == "uncertain":
                        status = "uncertain"
                        all_uncertain_counts[region_name] += 1
                    elif isinstance(value, dict) and "error" in value:
                        status = "error"
                        all_error_counts[region_name] += 1
                    else:
                        all_success_counts[region_name] += 1

                    details.append({
                        "page": page_no + 1,
                        "region": region_name,
                        "item": item,
                        "value": value,
                        "status": status,
                    })

                    print(f"  {region_name:20s} {item:5s}: {str(value)[:30]:30s} ({status})")

            except Exception as e:
                print(f"  {region_name:20s}: ERROR - {str(e)[:50]}")
                for item in items:
                    details.append({
                        "page": page_no + 1,
                        "region": region_name,
                        "item": item,
                        "value": None,
                        "status": "error",
                    })

        print()

    # Summary
    print("=" * 100)
    print("SUMMARY (v4_rules -- 6-page test)")
    print("=" * 100)
    print()

    for region_name in ["basic_info_header", "basic_info_footer", "case_items", "existing_support", "new_options"]:
        total = all_success_counts.get(region_name, 0) + all_null_counts.get(region_name, 0) + \
                all_uncertain_counts.get(region_name, 0) + all_error_counts.get(region_name, 0)
        success = all_success_counts.get(region_name, 0)
        rate = (success / total * 100) if total > 0 else 0
        print(f"{region_name:20s}:")
        print(f"  Total={total:3d}  Success={success:3d}  Null={all_null_counts.get(region_name, 0):3d}  " + \
              f"Uncertain={all_uncertain_counts.get(region_name, 0):3d}  Error={all_error_counts.get(region_name, 0):3d}  Rate={rate:5.1f}%")

    print()

    # Save
    df_details = pd.DataFrame(details)
    output_file = OUTPUT_DIR / "phase6b_6pages_extraction_details_v4_rules.csv"
    df_details.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"Saved: {output_file.name} ({len(df_details)} rows)")

    # JSON summary
    summary_json = {
        "version": "v4_rules",
        "target_date": "2026/05/17",
        "test_scope": "small-scale (6 pages)",
        "target_pages": [p + 1 for p in TARGET_PAGE_INDICES],
        "details": details,
        "stats": {
            "basic_info_header": {
                "total": all_success_counts.get("basic_info_header", 0) + all_null_counts.get("basic_info_header", 0) + \
                         all_uncertain_counts.get("basic_info_header", 0),
                "success": all_success_counts.get("basic_info_header", 0),
                "null": all_null_counts.get("basic_info_header", 0),
                "uncertain": all_uncertain_counts.get("basic_info_header", 0),
            },
            "case_items": {
                "total": all_success_counts.get("case_items", 0) + all_null_counts.get("case_items", 0) + \
                         all_uncertain_counts.get("case_items", 0),
                "success": all_success_counts.get("case_items", 0),
                "null": all_null_counts.get("case_items", 0),
                "uncertain": all_uncertain_counts.get("case_items", 0),
            },
        }
    }

    json_file = OUTPUT_DIR / "phase6b_6pages_extraction_summary_v4_rules.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(summary_json, f, ensure_ascii=False, indent=2)
    print(f"Saved: {json_file.name}")

    print()
    print("✓ Small-scale test (v4_rules) complete. Ready for Phase 4b comparison.")


if __name__ == "__main__":
    main()
