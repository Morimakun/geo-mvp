"""
Compare new_options bounds AND prompt variants.

Finding from visual analysis:
  Current bounds (18,50,38,62) correctly captures the new_options table.
  The issue is primarily the PROMPT, not the bounds.

  Phase 6B1 test (Japanese detailed prompt) → GS=1, GU=1 on Page 0
  30-page eval (English simple prompt) → all null

Strategy:
  Test 3 bounds × 2 prompts = 6 combinations on 7 pages = 42 API calls
"""

import sys
import os
import base64
import time
import json
from pathlib import Path
from io import BytesIO

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

client = Anthropic(api_key=api_key)

PDF_PATH = Path(__file__).parent.parent / "tests/fixtures/geo_pdf_reconciliation/20260529130020168.pdf"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs" / "phase6b_new_options_bounds_compare"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEST_PAGES = [0, 1, 3, 7, 10, 12, 15]

# Bounds to test
BOUNDS = {
    "current_38_62": {
        "bounds": (18, 50, 38, 62),
        "zoom": 4,
        "desc": "Current (original Phase 6B1)"
    },
    "wider_35_70": {
        "bounds": (18, 50, 35, 70),
        "zoom": 4,
        "desc": "Candidate A: wider right"
    },
    "much_wider_30_75": {
        "bounds": (15, 55, 30, 75),
        "zoom": 3,
        "desc": "Candidate C: much wider, lower zoom"
    },
}

# Prompt variants
PROMPT_ENGLISH_SIMPLE = """You are looking at the new options section of a Japanese daily report FAX form.

Read the handwritten numbers for these numbered items:
- "1. eo Phone" -> GS
- "2. Digital BS" -> GT
- "3. CS" -> GU

If the mark is unclear (e.g. could be a tally mark or line), return null.
Only return a number if you are confident.

Return ONLY this JSON format:
{
  "GS": number or null,
  "GT": number or null,
  "GU": number or null
}"""

PROMPT_JAPANESE_DETAILED = """あなたは日報FAX帳票の【新規オプション等】の領域を見ています。

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
  "GU": 数値またはnull,
  "warnings": []
}

見つからない項目は 0 ではなく null で返してください。
"""

PROMPTS = {
    "english_simple": PROMPT_ENGLISH_SIMPLE,
    "japanese_detailed": PROMPT_JAPANESE_DETAILED,
}


def extract_region_image(pdf_path, page_no, bounds, zoom):
    """Extract region from PDF and save as PNG."""
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

    return buf.getvalue(), img


def call_vision_api(image_bytes, prompt):
    """Call Claude Vision API."""
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
    print("=" * 80)
    print("Compare new_options: bounds x prompt combinations")
    print("=" * 80)

    if not PDF_PATH.exists():
        print("ERROR: PDF not found")
        return

    all_results = []

    # Save crop images for each bounds on each page
    print("\n--- Saving crop images ---")
    for page_no in TEST_PAGES:
        for bounds_name, config in BOUNDS.items():
            img_bytes, img = extract_region_image(
                PDF_PATH, page_no, config["bounds"], config["zoom"]
            )
            png_path = OUTPUT_DIR / f"page{page_no}_new_options_{bounds_name}.png"
            img.save(str(png_path), format="PNG")
    print("Crop images saved.")

    # Run extraction for each combination
    total_calls = len(TEST_PAGES) * len(BOUNDS) * len(PROMPTS)
    call_count = 0

    for page_no in TEST_PAGES:
        print(f"\n--- Page {page_no} ---")

        for bounds_name, config in BOUNDS.items():
            img_bytes, _ = extract_region_image(
                PDF_PATH, page_no, config["bounds"], config["zoom"]
            )

            for prompt_name, prompt_text in PROMPTS.items():
                call_count += 1
                combo = f"{bounds_name}+{prompt_name}"
                print(f"  [{call_count}/{total_calls}] {combo}...", end=" ")

                result = call_vision_api(img_bytes, prompt_text)

                gs = result.get("GS")
                gt = result.get("GT")
                gu = result.get("GU")
                warnings = result.get("warnings", [])
                error = result.get("error")

                null_count = sum(1 for v in [gs, gt, gu] if v is None)
                has_value = null_count < 3

                print(f"GS={gs} GT={gt} GU={gu} nulls={null_count}")

                all_results.append({
                    "page_number": page_no,
                    "bounds_name": bounds_name,
                    "bounds": str(config["bounds"]),
                    "zoom": config["zoom"],
                    "prompt_name": prompt_name,
                    "GS": gs,
                    "GT": gt,
                    "GU": gu,
                    "null_count": null_count,
                    "has_value": has_value,
                    "warnings": str(warnings)[:100] if warnings else "",
                    "error": str(error)[:50] if error else "",
                    "notes": config["desc"]
                })

                time.sleep(0.5)

    # Analysis
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    # Group by bounds+prompt
    combos = {}
    for r in all_results:
        key = f"{r['bounds_name']}+{r['prompt_name']}"
        if key not in combos:
            combos[key] = {"pages": 0, "null_sum": 0, "has_value_count": 0, "gs_values": [], "gt_values": [], "gu_values": []}
        combos[key]["pages"] += 1
        combos[key]["null_sum"] += r["null_count"]
        if r["has_value"]:
            combos[key]["has_value_count"] += 1
        if r["GS"] is not None:
            combos[key]["gs_values"].append((r["page_number"], r["GS"]))
        if r["GT"] is not None:
            combos[key]["gt_values"].append((r["page_number"], r["GT"]))
        if r["GU"] is not None:
            combos[key]["gu_values"].append((r["page_number"], r["GU"]))

    print("\nNull avg and value extraction by combination:")
    for key, stats in sorted(combos.items(), key=lambda x: x[1]["null_sum"]):
        null_avg = stats["null_sum"] / stats["pages"]
        print(f"\n  {key}:")
        print(f"    Pages with any value: {stats['has_value_count']}/{stats['pages']}")
        print(f"    Null avg: {null_avg:.2f}/3")
        if stats["gs_values"]:
            print(f"    GS values: {stats['gs_values']}")
        if stats["gt_values"]:
            print(f"    GT values: {stats['gt_values']}")
        if stats["gu_values"]:
            print(f"    GU values: {stats['gu_values']}")

    # Save CSV
    import pandas as pd
    df = pd.DataFrame(all_results)
    csv_path = Path(__file__).parent.parent / "data" / "test_outputs" / "phase6b_new_options_bounds_compare.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nCSV saved: {csv_path.name}")

    # Save JSON
    json_path = OUTPUT_DIR / "comparison_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "test_pages": TEST_PAGES,
            "bounds_tested": {k: {"bounds": v["bounds"], "zoom": v["zoom"]} for k, v in BOUNDS.items()},
            "prompts_tested": list(PROMPTS.keys()),
            "results": all_results,
        }, f, ensure_ascii=False, indent=2)

    # Recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)

    best = min(combos.items(), key=lambda x: x[1]["null_sum"])
    print(f"\nBest combination: {best[0]}")
    print(f"  Null avg: {best[1]['null_sum'] / best[1]['pages']:.2f}")
    print(f"  Pages with values: {best[1]['has_value_count']}/{best[1]['pages']}")


if __name__ == "__main__":
    main()
