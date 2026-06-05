"""
Fix HI=40 misread by adjusting existing_support bounds and prompt

Issue:
  Current bounds (12, 22, 58, 100) shows the table with template values like "40"
  These are NOT handwritten data - they are printed template numbers
  The actual handwritten entry cells are to the RIGHT of these numbers

Solution:
  1. Adjust bounds to focus on the right-side entry cells only
  2. Strengthen prompt to ONLY read handwritten values
  3. Ignore template numbers and item labels

Testing:
  Pages 0, 1, 3, 7, 15 (same as before)
"""

import sys
import os
import time
import json
import base64
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
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs" / "phase6b_hi40_fix"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Adjusted bounds - focus on right-side entry cells only
# Original was (12, 22, 58, 100) - too far left, showing template values
# New: (12, 22, 75, 100) - focus on right entry cells
ADJUSTED_BOUNDS = (12, 22, 75, 100)
ADJUSTED_ZOOM = 3

# Pages to test
TEST_PAGES = [0, 1, 3, 7, 15]

# Improved prompt that ignores template values
IMPROVED_PROMPT = """You are looking at the existing support section of a Japanese daily report FAX form.

CRITICAL: This section has a TABLE with:
- Left column: Item labels (e.g., "1. ネット追加", "2. 電話追加")
- Middle column: TEMPLATE NUMBERS (printed values like "40", "15", etc.) - IGNORE THESE
- Right column: HANDWRITTEN ENTRY CELLS (where actual numbers are written by hand)

You may see the middle column with printed numbers. IGNORE them completely.
Read ONLY the handwritten numbers in the right-side entry cells.

Extract exactly 3 items:
- HH: Handwritten value for row "1. ネット追加" (Net addition)
- HI: Handwritten value for row "2. 電話追加" (Phone addition)
- HJ: Handwritten value for row "3. テレビ追加" (TV addition)

Rules:
- Ignore any printed/template numbers (like "40", "15")
- If the right-side cell is empty or blank, return null
- If handwritten mark is unclear, return null
- If you see tally marks (正の字), count complete marks as 5
- Dashes (—, ー) mean 0
- Only return numbers you are CONFIDENT were written by hand

Return ONLY this JSON:
{
  "HH": number or null,
  "HI": number or null,
  "HJ": number or null
}"""


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
    print("Fix HI=40 Misread: existing_support bounds and prompt adjustment")
    print("=" * 80)
    print("\nAdjusted bounds: " + str(ADJUSTED_BOUNDS) + " (was (12, 22, 58, 100))")
    print("Zoom: " + str(ADJUSTED_ZOOM))
    print("Prompt: Ignore template values, read handwritten entry cells only")

    if not PDF_PATH.exists():
        print("\nERROR: PDF not found")
        return

    results = []

    print("\n" + "=" * 80)
    print("Testing adjusted extraction on Pages 0, 1, 3, 7, 15")
    print("=" * 80)

    for page_no in TEST_PAGES:
        print("\n--- Page " + str(page_no) + " ---")

        try:
            img_bytes = extract_region_image(PDF_PATH, page_no, ADJUSTED_BOUNDS, ADJUSTED_ZOOM)
            result = call_vision_api(img_bytes, IMPROVED_PROMPT)

            if "error" in result:
                print("  ERROR: " + str(result["error"])[:50])
                hh = hi = hj = None
            else:
                hh = result.get("HH")
                hi = result.get("HI")
                hj = result.get("HJ")
                print(f"  HH (ネット追加): {hh}")
                print(f"  HI (電話追加): {hi}")
                print(f"  HJ (テレビ追加): {hj}")

            results.append({
                "page": page_no,
                "HH": hh,
                "HI": hi,
                "HJ": hj,
                "raw": result
            })

        except Exception as e:
            print("  EXCEPTION: " + str(e)[:50])
            results.append({
                "page": page_no,
                "error": str(e)[:100]
            })

        time.sleep(0.5)

    # Summary
    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)

    print("\nPage | HH | HI | HJ")
    print("-" * 40)
    for r in results:
        page = r.get("page")
        hh = str(r.get("HH", "error"))[:10]
        hi = str(r.get("HI", "error"))[:10]
        hj = str(r.get("HJ", "error"))[:10]
        print(f"  {page:2d} | {hh:10s} | {hi:10s} | {hj:10s}")

    # Check if HI=40 is gone
    print("\n" + "=" * 80)
    print("DIAGNOSIS")
    print("=" * 80)

    hi_40_count = sum(1 for r in results if r.get("HI") == 40)
    hi_40_pages = [r.get("page") for r in results if r.get("HI") == 40]

    print("\nHI=40 occurrences: " + str(hi_40_count) + " (was 5 before)")
    if hi_40_count > 0:
        print("  Pages: " + str(hi_40_pages))
        print("  Status: ISSUE NOT FULLY RESOLVED - bounds may need further adjustment")
    else:
        print("  Status: HI=40 RESOLVED! bounds adjustment successful")

    # Save results
    results_json = OUTPUT_DIR / "fix_results.json"
    with open(results_json, "w", encoding="utf-8") as f:
        json.dump({
            "adjusted_bounds": ADJUSTED_BOUNDS,
            "original_bounds": (12, 22, 58, 100),
            "prompt_changed": True,
            "test_pages": TEST_PAGES,
            "results": results,
            "summary": {
                "hi_40_count": hi_40_count,
                "hi_40_pages": hi_40_pages,
                "status": "RESOLVED" if hi_40_count == 0 else "PARTIAL"
            }
        }, f, ensure_ascii=False, indent=2)

    print("\nResults saved: " + str(results_json))


if __name__ == "__main__":
    main()
