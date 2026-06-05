"""
Phase 6B: Evaluate extraction across all 30 real PDF pages

Uses existing region definitions from test_phase6b1_region_cases.py.
Runs 5 regions x 30 pages = 150 Vision API calls.

Outputs:
- data/test_outputs/phase6b_30pages_extraction_summary.csv
- data/test_outputs/phase6b_30pages_extraction_details.csv
- Console summary
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

# Region definitions (from test_phase6b1_region_cases.py REGIONS_SMALL)
REGIONS = {
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

    "case_items": {
        "bounds": (12, 24, 0, 45),
        "zoom": 3,
        "items": ["AU", "AV", "AY", "AZ", "AI"],
        "prompt": """You are looking at the case items section of a Japanese daily report FAX form.

Read the handwritten numbers in the "referral" column for each row:
- Row "au case new" -> AU
- Row "au case existing" -> AV
- Row "other case new" -> AY
- Row "other case existing" -> AZ
- Total row -> AI

If a cell has tally marks (Japanese "sei" character), count completed ones as 5.
If unclear, return null. Dashes mean 0.

Return ONLY this JSON format:
{
  "AU": number or null,
  "AV": number or null,
  "AY": number or null,
  "AZ": number or null,
  "AI": number or null
}"""
    },

    "existing_support": {
        "bounds": (12, 22, 65, 100),  # OPTIMIZED: Balanced view of template values + handwritten cells
        "zoom": 3,
        "items": ["HH", "HI", "HJ"],
        "prompt": """You are looking at the existing support section of a Japanese daily report FAX form.

CRITICAL: This section has a TABLE where:
- Left: Item labels (e.g., "1. ネット追加", "2. 電話追加", "3. テレビ追加")
- Middle: TEMPLATE PRINTED NUMBERS (like "40", "15") - IGNORE THESE
- Right: HANDWRITTEN ENTRY CELLS where users wrote actual numbers

You may see printed template numbers in the middle column. IGNORE them completely.
Read ONLY the HANDWRITTEN numbers in the right-side entry cells.

Extract these 3 items:
- HH: Handwritten value for "1. Net addition (ネット追加)"
- HI: Handwritten value for "2. Phone addition (電話追加)"
- HJ: Handwritten value for "3. TV addition (テレビ追加)"

Rules:
- Ignore ALL printed/template numbers (like "40", "15", etc.)
- Empty cells = null
- Unclear marks = null
- Tally marks (正の字): count complete marks as 5
- Dashes (—): treat as 0
- Only return numbers that are clearly HANDWRITTEN

Return ONLY this JSON:
{
  "HH": number or null,
  "HI": number or null,
  "HJ": number or null
}"""
    },

    "new_options": {
        "bounds": (18, 50, 38, 62),  # Bounds confirmed correct via visual analysis
        "zoom": 4,
        "items": ["GS", "GT", "GU"],
        "prompt": """あなたは日報FAX帳票の【新規オプション等】の領域を見ています。

この表には番号付きの項目が並んでいます。上から順に：
- 「1. eo光電話」の数値 → GS として返す
- 「2. 地デジBS」の数値 → GT として返す
- 「3. CS」の数値 → GU として返す

【読み取り方法】:

この帳票の数値欄には複数の記入形式があります：

1. **アラビア数字** (1, 2, 3, など)
   → そのまま数値として返してください

2. **正の字カウント** (完成形「正」で5カウント)
   - 明確な横線1本「一」のような形 → 1
   - 完成した「正」の字 → 5
   - 途中形で画数が**確実に判断できる場合**のみ → 2, 3, 4

3. **判断が難しい場合** (T字形・罫線と重なる・書き癖がある)
   → 無理に数値化せず null で返し、理由を warnings に記載してください

【重要な注意】:
- 数値が明確でない場合は、null を優先してください
- T字形・複数本の短い線・罫線と重なる形は「確実に2」と断定しないでください
- 「こう見える可能性がある」という推測ではなく「確実に見える」と判断できる場合だけ数値を返してください
- 空欄は null です

必ず以下のJSON形式で返してください：
{
  "GS": 数値またはnull,
  "GT": 数値またはnull,
  "GU": 数値またはnull
}

見つからない項目は 0 ではなく null で返してください。
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
    print("Phase 6B: 30-Page Extraction Evaluation")
    print("=" * 70)

    if not PDF_PATH.exists():
        print("ERROR: PDF not found: " + str(PDF_PATH))
        return

    doc = fitz.open(str(PDF_PATH))
    total_pages = len(doc)
    doc.close()
    print("PDF pages: " + str(total_pages))

    # Collect all results
    all_details = []
    region_stats = defaultdict(lambda: {"total": 0, "success": 0, "null": 0, "uncertain": 0, "error": 0})

    for page_no in range(total_pages):
        print("\n--- Page " + str(page_no) + " ---")

        for region_name, region_config in REGIONS.items():
            try:
                img_bytes = extract_region_image(
                    PDF_PATH, page_no,
                    region_config["bounds"],
                    region_config["zoom"]
                )

                result = call_vision_api(img_bytes, region_config["prompt"])

                if "error" in result:
                    print("  " + region_name + ": ERROR " + str(result["error"])[:40])
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

                # Filter out non-item keys (like "warnings")
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

                # Brief log
                items = region_config["items"]
                vals = [str(result.get(i, "null"))[:8] for i in items]
                print("  " + region_name + ": " + " ".join(vals))

            except Exception as e:
                print("  " + region_name + ": EXCEPTION " + str(e)[:40])
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

            # Rate limit: pause between API calls
            time.sleep(0.5)

    # Output summary
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
        print(region_name + ":")
        print("  Total: " + str(s["total"]) + "  Success: " + str(s["success"]) +
              "  Null: " + str(s["null"]) + "  Uncertain: " + str(s["uncertain"]) +
              "  Error: " + str(s["error"]) + "  Rate: " + str(round(rate, 1)) + "%")

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
    print("\nOVERALL: " + str(success_all) + "/" + str(total_all) +
          " = " + str(round(overall_rate, 1)) + "%")

    # Save CSV files
    summary_df = pd.DataFrame(summary_rows)
    summary_df.to_csv(OUTPUT_DIR / "phase6b_30pages_extraction_summary.csv", index=False, encoding="utf-8-sig")
    print("\nSaved: phase6b_30pages_extraction_summary.csv")

    details_df = pd.DataFrame(all_details)
    details_df.to_csv(OUTPUT_DIR / "phase6b_30pages_extraction_details.csv", index=False, encoding="utf-8-sig")
    print("Saved: phase6b_30pages_extraction_details.csv")

    # Save results JSON for reuse
    results_json = {
        "summary": summary_rows,
        "details": all_details,
        "total_pages": total_pages,
        "overall_success_rate": round(overall_rate, 1),
    }
    with open(OUTPUT_DIR / "phase6b_30pages_results.json", "w", encoding="utf-8") as f:
        json.dump(results_json, f, ensure_ascii=False, indent=2)
    print("Saved: phase6b_30pages_results.json")


if __name__ == "__main__":
    main()
