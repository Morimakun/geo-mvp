"""
Phase 6B v5.2: Split Crop with Bounds Optimization

Hypothesis: v5 failure was due to crop bounds, not prompt.
  - AI row height 0.5% is too small (crop: 24.0-24.5)
  - AV row may have boundary issues
  - AY row may have boundary issues

Strategy: Test multiple bounds configurations
  - Keep prompt unchanged (v5_fixedのまま)
  - Adjust only bounds
  - Compare AI, AV, AY extraction success

Scope: 7 pages (same as v5)
"""

import sys
import os

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
CROP_DIR = OUTPUT_DIR / "phase6b_v52_case_items_crops"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
CROP_DIR.mkdir(parents=True, exist_ok=True)

TEST_PAGES = [0, 5, 7, 8, 9, 14, 27]

# v5.2 Bounds configurations
BOUNDS_CONFIGS = {
    "v5_original": {
        "AU": (12.0, 15.5, 0, 45),
        "AV": (15.5, 19.0, 0, 45),
        "AY": (19.0, 21.5, 0, 45),
        "AZ": (21.5, 24.0, 0, 45),
        "AI": (24.0, 24.5, 0, 45),  # Too small height
    },
    "ai_large": {
        "AU": (12.0, 15.5, 0, 45),
        "AV": (15.5, 19.0, 0, 45),
        "AY": (19.0, 21.5, 0, 45),
        "AZ": (21.5, 24.0, 0, 45),
        "AI": (23.0, 26.0, 0, 45),  # Larger height
    },
    "ai_large_av_adjusted": {
        "AU": (12.0, 15.5, 0, 45),
        "AV": (15.0, 19.5, 0, 45),  # Adjusted
        "AY": (19.0, 21.5, 0, 45),
        "AZ": (21.5, 24.0, 0, 45),
        "AI": (23.0, 26.0, 0, 45),  # Larger
    },
    "ai_huge_av_ay_adjusted": {
        "AU": (12.0, 15.5, 0, 45),
        "AV": (14.5, 20.0, 0, 45),  # Wider bounds
        "AY": (18.5, 22.5, 0, 45),  # Wider bounds
        "AZ": (21.5, 24.0, 0, 45),
        "AI": (22.5, 26.5, 0, 45),  # Even larger
    },
}

# Prompts from v5_fixed (unchanged)
PROMPT_TALLY = """You are looking at a single row of the case items section.

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

PROMPT_NUMERIC = """You are looking at the total row of the case items section.

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

    rect = page.bound()
    page_width, page_height = rect.width, rect.height

    top, bottom, left, right = bounds
    top_px = int(page_height * top / 100)
    bottom_px = int(page_height * bottom / 100)
    left_px = int(page_width * left / 100)
    right_px = int(page_width * right / 100)

    crop_rect = fitz.Rect(left_px, top_px, right_px, bottom_px)
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

        try:
            result = json.loads(response_text)
            return result.get("value")
        except json.JSONDecodeError:
            if "null" in response_text.lower():
                return None
            elif "uncertain" in response_text.lower():
                return "uncertain"
            else:
                return None

    except Exception as e:
        print(f"  API error: {type(e).__name__}")
        return None

def run_bounds_test():
    """Test multiple bounds configurations."""

    print("=" * 80)
    print("Phase 6B v5.2: Bounds Optimization Test")
    print("=" * 80)
    print()

    all_results = []

    for config_name, bounds_dict in BOUNDS_CONFIGS.items():
        print(f"\nTesting configuration: {config_name}")
        print("-" * 80)

        config_results = []

        for page_idx in TEST_PAGES:
            pdf_page_num = page_idx + 1

            for field_code in ["AU", "AV", "AY", "AZ", "AI"]:
                bounds = bounds_dict[field_code]
                crop = crop_page(PDF_PATH, page_idx, bounds, zoom=3)

                # Save crop
                crop_filename = f"p{pdf_page_num:03d}_{field_code}_{config_name}.png"
                crop_path = CROP_DIR / crop_filename
                crop.save(crop_path)

                # Extract
                b64 = image_to_base64(crop)

                if field_code == "AI":
                    prompt = PROMPT_NUMERIC
                else:
                    prompt = PROMPT_TALLY

                v52_value = extract_with_vision(b64, prompt)

                config_results.append({
                    "config": config_name,
                    "pdf_page_number": f"P{pdf_page_num}",
                    "page_index": page_idx,
                    "field_code": field_code,
                    "v52_value": v52_value,
                    "bounds": str(bounds),
                })

            time.sleep(0.5)  # Rate limiting

        # Summarize this config
        df_config = pd.DataFrame(config_results)

        non_null = (~df_config['v52_value'].isna()).sum()
        ai_subset = df_config[df_config['field_code'] == 'AI']
        ai_non_null = (~ai_subset['v52_value'].isna()).sum()

        print(f"  Results: {non_null}/35 non-null ({100*non_null//35}%)")
        print(f"  AI results: {ai_non_null}/7 non-null")

        all_results.extend(config_results)

    # Save all results
    df_all = pd.DataFrame(all_results)
    output_csv = OUTPUT_DIR / "phase6b_v52_bounds_test.csv"
    df_all.to_csv(output_csv, index=False, encoding="utf-8-sig")

    print()
    print("=" * 80)
    print("Summary by Configuration")
    print("=" * 80)
    print()

    for config_name in BOUNDS_CONFIGS.keys():
        config_data = df_all[df_all['config'] == config_name]
        non_null = (~config_data['v52_value'].isna()).sum()
        ai_data = config_data[config_data['field_code'] == 'AI']
        ai_non_null = (~ai_data['v52_value'].isna()).sum()

        print(f"{config_name:30} | non-null: {non_null:2}/35 | AI: {ai_non_null}/7")

    print()
    print(f"Results saved to: {output_csv}")
    print("Crop images saved to:", CROP_DIR)

    return df_all

if __name__ == "__main__":
    df_results = run_bounds_test()
    print()
    print("Bounds optimization test completed.")
