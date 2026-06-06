"""
Phase 6B v5: case_items Split Crop Testing (Small-Scale)

Purpose:
  Evaluate whether splitting case_items (AU/AV/AY/AZ/AI) into individual row crops
  improves extraction accuracy and reduces tally mark misreading.

Scope:
  - 7 pages: P1(idx0), P6(idx5), P8(idx7), P9(idx8), P10(idx9), P15(idx14), P28(idx27)
  - NOT full 30 pages (small-scale only)

Comparison:
  - v3: Current unified crop for AU/AV/AY/AZ/AI (baseline)
  - v5: Individual row crops, each with appropriate prompt
    - AU/AV/AY/AZ: tally mark-focused prompt
    - AI: numeric digit-focused prompt

Outputs:
  data/test_outputs/phase6b_v5_case_items_split_test.csv
  data/test_outputs/phase6b_v5_case_items_crops/*.png
  docs/PHASE_6B_V5_CASE_ITEMS_SPLIT_TEST_RESULT.md
"""

import json
import base64
import sys
import os
import time
from pathlib import Path
from io import BytesIO
from collections import defaultdict

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

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
CROP_DIR = OUTPUT_DIR / "phase6b_v5_case_items_crops"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CROP_DIR.mkdir(parents=True, exist_ok=True)

# Test target pages (small-scale)
TEST_PAGES = [0, 5, 7, 8, 9, 14, 27]  # P1, P6, P8, P9, P10, P15, P28 (0-indexed)

# Case items row boundaries (% of page height)
# These are estimated based on PDF structure
CASE_ITEMS_ROWS = {
    "AU": {"top": 12, "bottom": 15.5, "left": 0, "right": 45, "name": "au案件新規"},
    "AV": {"top": 15.5, "bottom": 19, "left": 0, "right": 45, "name": "au案件既存"},
    "AY": {"top": 19, "bottom": 21.5, "left": 0, "right": 45, "name": "その他案件新規"},
    "AZ": {"top": 21.5, "bottom": 24, "left": 0, "right": 45, "name": "その他案件既存"},
    "AI": {"top": 24, "bottom": 24.5, "left": 0, "right": 45, "name": "合計"},
}

# ================================================================================
# PROMPT DEFINITIONS
# ================================================================================

PROMPT_V3_UNIFIED = """You are looking at the case items section of a Japanese daily report FAX form.

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
   - If the digit is ambiguous: return "uncertain"

4. OTHER:
   - Dash: 0
   - Grid lines, borders, printed template text: ignore completely

Return ONLY this JSON:
{
  "AU": number or "uncertain" or null,
  "AV": number or "uncertain" or null,
  "AY": number or "uncertain" or null,
  "AZ": number or "uncertain" or null,
  "AI": number or "uncertain" or null
}"""

PROMPT_V5_TALLY = """You are looking at a single row of the case items section of a Japanese daily report FAX form.

This row contains handwritten tally marks (正の字) OR numbers.

Extract ONLY the value in the "referral" (紹介) column for this row.

Rules:
- EMPTY cell (no handwriting) → null
- Clearly handwritten "0" → 0
- Tally marks (正の字):
  - 1 stroke: 1
  - 2 strokes (T/cross): 2
  - 3 strokes: 3
  - 4 strokes: 4
  - 5 strokes (complete 正): 5
  - Unclear: uncertain
- Handwritten digit: return the number
- Printed text/grid lines: ignore

Return ONLY a JSON number, "uncertain", or null:
{
  "value": number or "uncertain" or null
}"""

PROMPT_V5_NUMERIC = """You are looking at the total row of the case items section of a Japanese daily report FAX form.

This row contains handwritten NUMBERS ONLY (not tally marks).

Extract the total value from the "referral" (紹介) column.

Rules:
- EMPTY cell (no handwriting) → null
- Handwritten digit(s) → return as number
- Ambiguous digit → uncertain
- Do NOT count tally marks (this is a numeric field)
- Printed text/grid lines: ignore

Return ONLY a JSON number, "uncertain", or null:
{
  "value": number or "uncertain" or null
}"""

# ================================================================================
# EXTRACTION FUNCTIONS
# ================================================================================

def crop_page(pdf_path, page_index, bounds, zoom=1):
    """
    Extract a cropped region from a PDF page.
    bounds: (top%, bottom%, left%, right%)
    zoom: magnification factor
    Returns: PIL Image
    """
    pdf = fitz.open(pdf_path)
    page = pdf[page_index]

    # Get page dimensions
    rect = page.bound()
    page_width, page_height = rect.width, rect.height

    # Convert percentage bounds to pixel coordinates
    top, bottom, left, right = bounds
    top_px = int(page_height * top / 100)
    bottom_px = int(page_height * bottom / 100)
    left_px = int(page_width * left / 100)
    right_px = int(page_width * right / 100)

    # Crop region
    crop_rect = fitz.Rect(left_px, top_px, right_px, bottom_px)

    # Render to image
    pix = page.get_pixmap(clip=crop_rect, matrix=fitz.Matrix(zoom, zoom))
    img_data = pix.tobytes("ppm")
    img = Image.open(BytesIO(img_data))

    pdf.close()
    return img

def image_to_base64(img):
    """Convert PIL Image to base64 string."""
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    img_str = base64.standard_b64encode(buffered.getvalue()).decode()
    return img_str

def extract_with_vision(image_b64, prompt, model="claude-sonnet-4-6"):
    """Call Claude API with vision to extract data."""
    try:
        message = client.messages.create(
            model=model,
            max_tokens=200,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        }
                    ],
                }
            ],
        )

        response_text = message.content[0].text.strip()

        # Parse JSON
        try:
            result = json.loads(response_text)
            return result
        except json.JSONDecodeError:
            print(f"Warning: Could not parse JSON: {response_text}")
            return None

    except Exception as e:
        print(f"Error in Vision API call: {e}")
        return None

# ================================================================================
# MAIN TESTING
# ================================================================================

def run_test():
    """Run small-scale split crop test."""

    print("=" * 80)
    print("Phase 6B v5: case_items Split Crop Test (7 pages)")
    print("=" * 80)
    print()

    results = []

    for page_idx in TEST_PAGES:
        pdf_page_num = page_idx + 1
        print(f"Processing page P{pdf_page_num} (index {page_idx})...")

        # ---- V3: Unified crop (baseline) ----
        unified_crop = crop_page(PDF_PATH, page_idx, (12, 24, 0, 45), zoom=3)
        unified_b64 = image_to_base64(unified_crop)
        v3_result = extract_with_vision(unified_b64, PROMPT_V3_UNIFIED)

        # ---- V5: Individual row crops ----
        v5_results = {}

        for field_code, row_config in CASE_ITEMS_ROWS.items():
            bounds = (row_config["top"], row_config["bottom"], row_config["left"], row_config["right"])
            crop = crop_page(PDF_PATH, page_idx, bounds, zoom=3)

            # Save crop image
            crop_filename = f"p{pdf_page_num:03d}_{field_code}.png"
            crop_path = CROP_DIR / crop_filename
            crop.save(crop_path)

            # Extract with appropriate prompt
            b64 = image_to_base64(crop)

            if field_code == "AI":
                # Numeric prompt for total row
                prompt = PROMPT_V5_NUMERIC
            else:
                # Tally mark prompt for case rows
                prompt = PROMPT_V5_TALLY

            v5_response = extract_with_vision(b64, prompt)
            if v5_response:
                v5_results[field_code] = v5_response.get("value")
            else:
                v5_results[field_code] = None

        # ---- Comparison ----
        for field_code in ["AU", "AV", "AY", "AZ", "AI"]:
            v3_val = v3_result.get(field_code) if v3_result else None
            v5_val = v5_results.get(field_code)

            # Determine comparison status
            if v3_val == v5_val:
                status = "SAME"
            elif v3_val is None and v5_val is not None:
                status = "V5_IMPROVED_NULL"
            elif v3_val is not None and v5_val is None:
                status = "V3_BETTER_VALUE"
            elif v3_val == "uncertain" and v5_val in [0, 1, 2, 3, 4, 5]:
                status = "V5_IMPROVED_UNCERTAIN"
            else:
                status = "DIFFERENCE"

            results.append({
                "pdf_page_number": f"P{pdf_page_num}",
                "page_index": page_idx,
                "field_code": field_code,
                "field_name": CASE_ITEMS_ROWS[field_code]["name"],
                "v3_value": v3_val,
                "v5_value": v5_val,
                "comparison_status": status,
                "expected_type": "numeric" if field_code == "AI" else "tally/numeric",
                "improvement": "yes" if status in ["V5_IMPROVED_NULL", "V5_IMPROVED_UNCERTAIN"] else "no",
            })

        print(f"  OK P{pdf_page_num} done")
        time.sleep(1)  # Rate limiting

    # Save results to CSV
    df = pd.DataFrame(results)
    output_csv = OUTPUT_DIR / "phase6b_v5_case_items_split_test.csv"
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print()
    print(f"Results saved to: {output_csv}")

    # Summary statistics
    total = len(results)
    improved = sum(1 for r in results if r["improvement"] == "yes")
    same = sum(1 for r in results if r["comparison_status"] == "SAME")

    print()
    print("=" * 80)
    print("Summary Statistics:")
    print(f"  Total results: {total}")
    print(f"  Improved by v5: {improved} ({100*improved//total}%)")
    print(f"  Same (no change): {same}")
    print(f"  Crop images saved: {CROP_DIR}")
    print("=" * 80)
    print()

    return df

if __name__ == "__main__":
    df_results = run_test()
    print("\nTest completed. Next: Create detailed analysis report.")
