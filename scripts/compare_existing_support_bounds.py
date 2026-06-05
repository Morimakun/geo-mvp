"""
Compare existing_support bounds to find optimal extraction region

Compare 4 bounds on 7 pages:
- Old: (12, 22, 58, 100) ← item names visible, HI=40 misread
- Current: (12, 22, 75, 100) ← HI=40 fixed, but HH/HJ null increase
- Candidate A: (12, 22, 70, 100) ← middle ground
- Candidate B: (12, 22, 65, 100) ← wider view

Evaluate:
1. HI=40 re-emergence
2. HH/HJ/HI null rate
3. Visual crop clarity
4. Template value presence
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
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs" / "phase6b_existing_support_bounds_compare"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Bounds to compare
BOUNDS_TO_TEST = {
    "bounds_58_100": (12, 22, 58, 100),  # Original
    "bounds_65_100": (12, 22, 65, 100),  # Candidate B
    "bounds_68_100": (12, 22, 68, 100),  # Candidate C (optional)
    "bounds_70_100": (12, 22, 70, 100),  # Candidate A
    "bounds_75_100": (12, 22, 75, 100),  # Current
}

TEST_PAGES = [0, 1, 3, 7, 10, 12, 15]

# Fixed prompt (ignore template values)
PROMPT = """You are looking at the existing support section of a Japanese daily report FAX form.

CRITICAL: This section has TABLE structure where:
- Left: Item labels (e.g., "1. ネット追加", "2. 電話追加", "3. テレビ追加")
- Middle: TEMPLATE PRINTED NUMBERS (like "40", "15") - IGNORE THESE
- Right: HANDWRITTEN ENTRY CELLS (user-written numbers)

Ignore ALL printed/template numbers. Read ONLY handwritten numbers in right-side cells.

Extract 3 items:
- HH: Handwritten value for "1. Net addition (ネット追加)"
- HI: Handwritten value for "2. Phone addition (電話追加)"
- HJ: Handwritten value for "3. TV addition (テレビ追加)"

Rules:
- Ignore template numbers like "40", "15", etc.
- Empty cells = null
- Unclear = null
- Only return numbers you are CONFIDENT were handwritten

Return ONLY this JSON:
{
  "HH": number or null,
  "HI": number or null,
  "HJ": number or null
}"""


def extract_region_image(pdf_path, page_no, bounds, zoom=3):
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

    # Convert to JPEG bytes for API
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)

    # Save as PNG for visual inspection
    bounds_name = f"bounds_{int(left_pct)}_{int(right_pct)}"
    png_path = OUTPUT_DIR / f"page{page_no}_{bounds_name}.png"
    img.save(str(png_path), format="PNG")

    doc.close()

    return buf.getvalue()


def call_vision_api(image_bytes, prompt):
    """Call Claude Vision API."""
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
    print("Compare existing_support bounds")
    print("=" * 80)

    if not PDF_PATH.exists():
        print("ERROR: PDF not found")
        return

    all_results = []

    for page_no in TEST_PAGES:
        print(f"\n--- Page {page_no} ---")

        for bounds_name, bounds in BOUNDS_TO_TEST.items():
            print(f"  Testing {bounds_name}...")

            try:
                img_bytes = extract_region_image(PDF_PATH, page_no, bounds)
                result = call_vision_api(img_bytes, PROMPT)

                hh = result.get("HH")
                hi = result.get("HI")
                hj = result.get("HJ")

                # Count nulls
                null_count = sum(1 for v in [hh, hi, hj] if v is None)

                # Check for HI=40
                hi40_detected = (hi == 40)

                result_dict = {
                    "page_number": page_no,
                    "bounds_name": bounds_name,
                    "bounds": str(bounds),
                    "HH": hh,
                    "HI": hi,
                    "HJ": hj,
                    "hi40_detected": hi40_detected,
                    "null_count": null_count,
                    "notes": ""
                }

                # Add notes
                if hi40_detected:
                    result_dict["notes"] = "WARNING: HI=40 detected"
                elif null_count == 3:
                    result_dict["notes"] = "All null (crop may be too narrow)"
                elif null_count == 0:
                    result_dict["notes"] = "All values extracted"
                else:
                    result_dict["notes"] = f"{null_count} nulls"

                all_results.append(result_dict)

                print(f"    HH={hh}, HI={hi}, HJ={hj}, nulls={null_count}")

            except Exception as e:
                print(f"    ERROR: {str(e)[:50]}")
                all_results.append({
                    "page_number": page_no,
                    "bounds_name": bounds_name,
                    "bounds": str(bounds),
                    "HH": None,
                    "HI": None,
                    "HJ": None,
                    "hi40_detected": False,
                    "null_count": 3,
                    "notes": f"API ERROR: {str(e)[:30]}"
                })

            time.sleep(0.5)

    # Analysis
    print("\n" + "=" * 80)
    print("ANALYSIS")
    print("=" * 80)

    # Group by bounds
    bounds_summary = {}
    for result in all_results:
        bounds_name = result["bounds_name"]
        if bounds_name not in bounds_summary:
            bounds_summary[bounds_name] = {
                "pages": 0,
                "hi40_count": 0,
                "null_sum": 0,
                "null_avg": 0,
            }

        bounds_summary[bounds_name]["pages"] += 1
        if result["hi40_detected"]:
            bounds_summary[bounds_name]["hi40_count"] += 1
        bounds_summary[bounds_name]["null_sum"] += result["null_count"]

    print("\nSummary by bounds:")
    for bounds_name, stats in sorted(bounds_summary.items()):
        stats["null_avg"] = stats["null_sum"] / stats["pages"]
        print(f"  {bounds_name}:")
        print(f"    Pages: {stats['pages']}")
        print(f"    HI=40 count: {stats['hi40_count']}")
        print(f"    Null avg: {stats['null_avg']:.2f}/3")

    # Save results to CSV
    import pandas as pd
    df = pd.DataFrame(all_results)
    csv_path = Path(__file__).parent.parent / "data" / "test_outputs" / "phase6b_existing_support_bounds_compare.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\nResults saved: {csv_path.name}")

    # Save JSON
    json_path = OUTPUT_DIR / "comparison_results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({
            "test_pages": TEST_PAGES,
            "bounds_tested": BOUNDS_TO_TEST,
            "results": all_results,
            "summary": bounds_summary
        }, f, ensure_ascii=False, indent=2)
    print(f"JSON saved: {json_path.name}")

    print(f"\nCrop images saved: {OUTPUT_DIR}")

    # Print recommendation
    print("\n" + "=" * 80)
    print("RECOMMENDATION")
    print("=" * 80)

    best_bounds = min(bounds_summary.items(), key=lambda x: (x[1]["hi40_count"], x[1]["null_avg"]))
    print(f"\nRecommended bounds: {best_bounds[0]}")
    print(f"  HI=40 count: {best_bounds[1]['hi40_count']}")
    print(f"  Null avg: {best_bounds[1]['null_avg']:.2f}")


if __name__ == "__main__":
    main()
