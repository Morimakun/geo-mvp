"""
Verify HI=40 fix by rerunning existing_support extraction on Pages 0-15

Compares:
  Before: Original bounds (12, 22, 58, 100)
  After: Modified bounds (12, 22, 75, 100) with stronger prompt

Goal: Confirm HI=40 is eliminated
"""

import json
import base64
import sys
import os
import time
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
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Modified existing_support configuration
REGION_CONFIG = {
    "bounds": (12, 22, 75, 100),  # Modified: shifted right
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
}

TEST_PAGES = list(range(16))  # Pages 0-15


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
                max_tokens=256,
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
    print("=" * 80)
    print("Verify HI=40 Fix: existing_support rerun on Pages 0-15")
    print("=" * 80)
    print("\nModified bounds: " + str(REGION_CONFIG["bounds"]))
    print("Zoom: " + str(REGION_CONFIG["zoom"]))

    if not PDF_PATH.exists():
        print("\nERROR: PDF not found")
        return

    # Load before data
    before_json = OUTPUT_DIR / "phase6b_30pages_results.json"
    before_data = {}
    if before_json.exists():
        with open(before_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Extract existing_support data
            for d in data.get("details", []):
                if d.get("region") == "existing_support" and d.get("page") < 16:
                    key = (d["page"], d["item"])
                    before_data[key] = d.get("value")

    print("\nBefore fix data loaded: " + str(len(before_data)) + " items")

    # Run modified extraction
    after_data = {}
    results = []

    print("\n" + "=" * 80)
    print("Running modified extraction on Pages 0-15")
    print("=" * 80)

    for page_no in TEST_PAGES:
        print("\nPage " + str(page_no) + ":")

        try:
            img_bytes = extract_region_image(
                PDF_PATH, page_no,
                REGION_CONFIG["bounds"],
                REGION_CONFIG["zoom"]
            )

            result = call_vision_api(img_bytes, REGION_CONFIG["prompt"])

            if "error" in result:
                print("  ERROR: " + str(result["error"])[:50])
                hh = hi = hj = None
            else:
                hh = result.get("HH")
                hi = result.get("HI")
                hj = result.get("HJ")

                # Store for comparison
                after_data[(page_no, "HH")] = hh
                after_data[(page_no, "HI")] = hi
                after_data[(page_no, "HJ")] = hj

                before_hh = before_data.get((page_no, "HH"))
                before_hi = before_data.get((page_no, "HI"))
                before_hj = before_data.get((page_no, "HJ"))

                print(f"  HH: {before_hh} → {hh}")
                print(f"  HI: {before_hi} → {hi}")
                print(f"  HJ: {before_hj} → {hj}")

            results.append({
                "page": page_no,
                "HH_before": before_data.get((page_no, "HH")),
                "HH_after": hh,
                "HI_before": before_data.get((page_no, "HI")),
                "HI_after": hi,
                "HJ_before": before_data.get((page_no, "HJ")),
                "HJ_after": hj,
            })

        except Exception as e:
            print("  EXCEPTION: " + str(e)[:50])
            results.append({
                "page": page_no,
                "error": str(e)[:100]
            })

        time.sleep(0.5)

    # Analysis
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    hi_40_before = sum(1 for r in results if r.get("HI_before") == 40)
    hi_40_after = sum(1 for r in results if r.get("HI_after") == 40)

    print("\nHI=40 count:")
    print("  Before: " + str(hi_40_before) + " pages")
    print("  After: " + str(hi_40_after) + " pages")

    if hi_40_after == 0 and hi_40_before > 0:
        print("  Result: SUCCESS - HI=40 ELIMINATED")
    elif hi_40_after < hi_40_before:
        print("  Result: PARTIAL - HI=40 reduced but not fully eliminated")
    else:
        print("  Result: FAILED - HI=40 not resolved")

    # Check degradation
    hh_unchanged = sum(1 for r in results if r.get("HH_before") == r.get("HH_after"))
    hj_unchanged = sum(1 for r in results if r.get("HJ_before") == r.get("HJ_after"))

    print("\nConsistency check:")
    print("  HH unchanged: " + str(hh_unchanged) + "/16")
    print("  HJ unchanged: " + str(hj_unchanged) + "/16")

    # Save results
    import pandas as pd

    results_df = pd.DataFrame(results)
    csv_path = OUTPUT_DIR / "phase6b_hi40_after_fix_comparison.csv"
    results_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print("\nResults saved: " + str(csv_path.name))

    # Save JSON
    results_json = OUTPUT_DIR / "phase6b_hi40_fix_verification.json"
    with open(results_json, "w", encoding="utf-8") as f:
        json.dump({
            "test_pages": TEST_PAGES,
            "before_count_hi40": hi_40_before,
            "after_count_hi40": hi_40_after,
            "status": "SUCCESS" if hi_40_after == 0 else ("PARTIAL" if hi_40_after < hi_40_before else "FAILED"),
            "results": results
        }, f, ensure_ascii=False, indent=2)

    print("JSON saved: " + str(results_json.name))


if __name__ == "__main__":
    main()
