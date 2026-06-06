"""
Phase 6B v5: case_items Split Crop Testing (Small-Scale) - FIXED VERSION

Purpose:
  Test whether splitting case_items (AU/AV/AY/AZ/AI) into individual crops
  improves extraction compared to v3 unified crop.

Scope: 7 pages only (small-scale test)
"""

import sys
import os

# Fix Windows console encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import json
import base64
from pathlib import Path
from io import BytesIO
import time

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
CASE_ITEMS_ROWS = {
    "AU": {"top": 12, "bottom": 15.5, "left": 0, "right": 45, "name": "au case new"},
    "AV": {"top": 15.5, "bottom": 19, "left": 0, "right": 45, "name": "au case existing"},
    "AY": {"top": 19, "bottom": 21.5, "left": 0, "right": 45, "name": "other case new"},
    "AZ": {"top": 21.5, "bottom": 24, "left": 0, "right": 45, "name": "other case existing"},
    "AI": {"top": 24, "bottom": 24.5, "left": 0, "right": 45, "name": "total"},
}

# Prompts with NO special characters (no em-dashes, etc)
PROMPT_V5_TALLY = """You are looking at a single row of the case items section.

This row contains tally marks (count of strokes) or handwritten numbers.

Extract ONLY the value in the referral column for this row.

Rules:
- Empty cell (no writing) -> null
- 1 stroke -> 1
- 2 strokes (T or cross shape) -> 2
- 3 strokes -> 3
- 4 strokes -> 4
- 5 strokes (complete character) -> 5
- Handwritten digit -> return the digit
- Unclear -> uncertain

Return ONLY a JSON number, "uncertain", or null.
Example: {"value": 1} or {"value": null}"""

PROMPT_V5_NUMERIC = """You are looking at the total row of the case items section.

This row contains handwritten NUMBERS ONLY (not tally marks).

Extract the total value from the referral column.

Rules:
- Empty cell (no writing) -> null
- Handwritten digit(s) -> return as number
- Ambiguous digit -> uncertain
- Do NOT count tally marks
- Ignore printed text and grid lines

Return ONLY a JSON number, "uncertain", or null.
Example: {"value": 5} or {"value": null}"""

def crop_page(pdf_path, page_index, bounds, zoom=1):
    """Extract a cropped region from a PDF page."""
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
            max_tokens=100,
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

        # Try to parse JSON
        try:
            result = json.loads(response_text)
            return result.get("value")
        except json.JSONDecodeError:
            # Try to extract from text
            if "null" in response_text.lower():
                return None
            elif "uncertain" in response_text.lower():
                return "uncertain"
            else:
                # Last resort: return None
                return None

    except Exception as e:
        print(f"  API error: {type(e).__name__}")
        return None

def run_test():
    """Run small-scale split crop test."""

    print("=" * 80)
    print("Phase 6B v5: case_items Split Crop Test (Fixed)")
    print("=" * 80)
    print()

    results = []

    for page_idx in TEST_PAGES:
        pdf_page_num = page_idx + 1
        print(f"Processing page P{pdf_page_num:02d} (index {page_idx})...")

        # ---- V5: Individual row crops ----
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
                prompt = PROMPT_V5_NUMERIC
            else:
                prompt = PROMPT_V5_TALLY

            v5_value = extract_with_vision(b64, prompt)

            results.append({
                "pdf_page_number": f"P{pdf_page_num}",
                "page_index": page_idx,
                "field_code": field_code,
                "field_name": row_config["name"],
                "v5_value": v5_value,
            })

        print(f"  OK done")
        time.sleep(1)  # Rate limiting

    # Save results to CSV
    df = pd.DataFrame(results)
    output_csv = OUTPUT_DIR / "phase6b_v5_case_items_split_test_fixed.csv"
    df.to_csv(output_csv, index=False, encoding="utf-8-sig")
    print()
    print(f"Results saved to: {output_csv}")

    # Summary statistics
    total = len(results)
    empty = sum(1 for r in results if r["v5_value"] is None)
    uncertain = sum(1 for r in results if r["v5_value"] == "uncertain")
    numeric = sum(1 for r in results if isinstance(r["v5_value"], (int, float)))

    print()
    print("=" * 80)
    print("Summary:")
    print(f"  Total results: {total}")
    print(f"  Numeric values: {numeric} ({100*numeric//total}%)")
    print(f"  Uncertain: {uncertain}")
    print(f"  Null/empty: {empty} ({100*empty//total}%)")
    print("=" * 80)
    print()

    return df

if __name__ == "__main__":
    df_results = run_test()
    print("Test completed.")
