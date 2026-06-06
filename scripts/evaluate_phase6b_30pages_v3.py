"""
Phase 6B v3: 30-Page Extraction with Improved Prompts

Key improvements over v2:
  1. case_items: Blank/empty cells → null (not 0). Only return 0 for clearly handwritten "0".
  2. new_options: Stricter tally mark counting. Partial or unclear → uncertain (not a number).
  3. existing_support: Minor 0 vs blank distinction added.

Outputs:
  data/test_outputs/phase6b_30pages_results_v3.json
  data/test_outputs/phase6b_30pages_extraction_summary_v3.csv
  data/test_outputs/phase6b_30pages_extraction_details_v3.csv
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

# ================================================================================
# REGIONS v3 — Improved prompts
# bounds: (top%, bottom%, left%, right%)  zoom: int
# ================================================================================

REGIONS = {

    # ---- basic_info_header: unchanged (works well) ----
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

    # ---- basic_info_footer: unchanged (works well) ----
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

    # ---- case_items: IMPROVED ----
    # Key change: empty cells → null, not 0
    # Tally marks: all stages explained (1-5)
    # Handwritten numbers: uncertain if ambiguous
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

==== CRITICAL RULES ====

1. BLANK vs ZERO — most important distinction:
   - Cell is EMPTY (no handwriting at all) → return null
   - "0" clearly handwritten by the staff → return 0
   - Do NOT read printed template text, grid borders, or background lines as 0
   - When in doubt between blank and 0: return null

2. TALLY MARKS (正の字 "sei" character — vertical/horizontal stroke counting):
   - 1 horizontal stroke only: 1
   - 2 strokes (T-shape or cross-like): 2
   - 3 strokes: 3
   - 4 strokes: 4
   - Complete "正" character (5 clearly intersecting strokes): 5
   - Partial or unclear strokes → "uncertain"
   - IMPORTANT: Count only HANDWRITTEN lines. Template borders and grid lines do NOT count.

3. HANDWRITTEN ARABIC NUMBERS:
   - Return the number as-is if clearly readable
   - If the digit is ambiguous (e.g., could be 0 or 6, or 1 or 7): return "uncertain"

4. OTHER:
   - Dash (—): 0
   - Grid lines, borders, printed template text: ignore completely

Return ONLY this JSON:
{
  "AU": number or "uncertain" or null,
  "AV": number or "uncertain" or null,
  "AY": number or "uncertain" or null,
  "AZ": number or "uncertain" or null,
  "AI": number or "uncertain" or null
}"""
    },

    # ---- existing_support: SLIGHTLY IMPROVED ----
    # Key change: 0 vs blank distinction added (minor)
    "existing_support": {
        "bounds": (12, 22, 65, 100),
        "zoom": 3,
        "items": ["HH", "HI", "HJ"],
        "prompt": """You are looking at the existing support section of a Japanese daily report FAX form.

CRITICAL: This section has a TABLE where:
- Left: Item labels (e.g., "1. ネット追加", "2. 電話追加", "3. テレビ追加")
- Middle: TEMPLATE PRINTED NUMBERS (like "40", "15") — IGNORE THESE COMPLETELY
- Right: HANDWRITTEN ENTRY CELLS where staff wrote actual numbers

Extract:
- HH: Handwritten value for "1. Net addition (ネット追加)"
- HI: Handwritten value for "2. Phone addition (電話追加)"
- HJ: Handwritten value for "3. TV addition (テレビ追加)"

==== RULES ====

1. BLANK vs ZERO:
   - Entry cell is empty (no handwriting) → null
   - Staff clearly wrote "0" → 0
   - Do NOT read printed/template numbers as the handwritten value

2. TALLY MARKS (正の字):
   - 1 stroke: 1, 2 strokes: 2, 3 strokes: 3, 4 strokes: 4, complete "正": 5
   - Unclear/partial: null

3. TEMPLATE NUMBERS — IGNORE:
   - Ignore any numbers that appear to be part of the printed template (e.g., "40", "15" in middle column)
   - Only read values in the rightmost handwritten entry column

4. Dashes (—): 0

Return ONLY this JSON:
{
  "HH": number or null,
  "HI": number or null,
  "HJ": number or null
}"""
    },

    # ---- new_options: IMPROVED ----
    # Key change: stricter tally counting, partial/template lines → uncertain (not a number)
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


def call_vision_api(image_bytes, prompt):
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
    print("=" * 70)
    print("Phase 6B v3: 30-Page Extraction (Improved Prompts)")
    print("=" * 70)
    print()
    print("Key improvements:")
    print("  case_items: blank → null (not 0), tally stages 1-5, uncertain for ambiguous digits")
    print("  new_options: stricter tally (partial → uncertain), template lines ignored")
    print("  existing_support: minor 0 vs blank distinction added")
    print()

    if not PDF_PATH.exists():
        print("ERROR: PDF not found: " + str(PDF_PATH))
        return

    doc = fitz.open(str(PDF_PATH))
    total_pages = len(doc)
    doc.close()
    print(f"PDF pages: {total_pages}")

    all_details = []
    region_stats = defaultdict(lambda: {"total": 0, "success": 0, "null": 0, "uncertain": 0, "error": 0})

    for page_no in range(total_pages):
        print(f"\n--- Page {page_no} ---")

        for region_name, region_config in REGIONS.items():
            try:
                img_bytes = extract_region_image(
                    PDF_PATH, page_no,
                    region_config["bounds"],
                    region_config["zoom"]
                )

                result = call_vision_api(img_bytes, region_config["prompt"])

                if "error" in result:
                    print(f"  {region_name}: ERROR {str(result['error'])[:40]}")
                    region_stats[region_name]["error"] += 1
                    for item in region_config["items"]:
                        all_details.append({
                            "page": page_no,
                            "region": region_name,
                            "item": item,
                            "value": None,
                            "status": "error",
                            "raw": str(result.get("error", ""))[:50]
                        })
                        region_stats[region_name]["total"] += 1
                    continue

                for item in region_config["items"]:
                    value = result.get(item)
                    region_stats[region_name]["total"] += 1

                    if value is None:
                        status = "null"
                        region_stats[region_name]["null"] += 1
                    elif isinstance(value, str) and value.lower() in ("uncertain", "unreadable"):
                        status = "uncertain"
                        region_stats[region_name]["uncertain"] += 1
                    else:
                        status = "success"
                        region_stats[region_name]["success"] += 1

                    all_details.append({
                        "page": page_no,
                        "region": region_name,
                        "item": item,
                        "value": value,
                        "status": status,
                        "raw": ""
                    })

                items = region_config["items"]
                vals = [str(result.get(i, "null"))[:8] for i in items]
                print(f"  {region_name}: {' '.join(vals)}")

            except Exception as e:
                print(f"  {region_name}: EXCEPTION {str(e)[:40]}")
                region_stats[region_name]["error"] += 1
                for item in region_config["items"]:
                    all_details.append({
                        "page": page_no,
                        "region": region_name,
                        "item": item,
                        "value": None,
                        "status": "error",
                        "raw": str(e)[:50]
                    })
                    region_stats[region_name]["total"] += 1

            time.sleep(0.5)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    summary_rows = []
    total_all = 0
    success_all = 0
    null_all = 0

    for region_name in REGIONS.keys():
        s = region_stats[region_name]
        rate = s["success"] / s["total"] * 100 if s["total"] > 0 else 0
        print(f"{region_name}:")
        print(f"  Total={s['total']}  Success={s['success']}  Null={s['null']}  "
              f"Uncertain={s['uncertain']}  Error={s['error']}  Rate={rate:.1f}%")

        summary_rows.append({
            "region": region_name,
            "items_per_page": len(REGIONS[region_name]["items"]),
            "total_items": s["total"],
            "success": s["success"],
            "null": s["null"],
            "uncertain": s["uncertain"],
            "error": s["error"],
            "success_rate": round(rate, 1)
        })

        total_all += s["total"]
        success_all += s["success"]
        null_all += s["null"]

    overall_rate = success_all / total_all * 100 if total_all > 0 else 0
    print(f"\nOVERALL: {success_all}/{total_all} = {overall_rate:.1f}%")

    # Save
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUTPUT_DIR / "phase6b_30pages_extraction_summary_v3.csv", index=False, encoding="utf-8-sig")
    print("\nSaved: phase6b_30pages_extraction_summary_v3.csv")

    details_df = pd.DataFrame(all_details)
    details_df.to_csv(OUTPUT_DIR / "phase6b_30pages_extraction_details_v3.csv", index=False, encoding="utf-8-sig")
    print("Saved: phase6b_30pages_extraction_details_v3.csv")

    results_json = {
        "summary": summary_rows,
        "details": all_details,
        "total_pages": total_pages,
        "overall_success_rate": round(overall_rate, 1),
        "version": "v3",
        "prompt_changes": [
            "case_items: blank cells now return null instead of 0",
            "case_items: tally marks all stages 1-5 explained, uncertain for ambiguous",
            "new_options: stricter tally - partial/unclear marks return uncertain",
            "new_options: template lines explicitly excluded from tally count",
            "existing_support: 0 vs blank distinction added"
        ]
    }
    with open(OUTPUT_DIR / "phase6b_30pages_results_v3.json", "w", encoding="utf-8") as f:
        json.dump(results_json, f, ensure_ascii=False, indent=2)
    print("Saved: phase6b_30pages_results_v3.json")


if __name__ == "__main__":
    main()
