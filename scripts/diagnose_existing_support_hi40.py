"""
Diagnose HI=40 misread issue in existing_support region

Step 1: Extract crop images for Pages 0, 1, 3, 7, 15
Step 2: Save as PNG for visual inspection
Step 3: Read OCR raw response to understand what's being extracted
"""

import sys
import os
from pathlib import Path
import json
import base64
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
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs" / "phase6b_diagnosis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Current existing_support bounds
CURRENT_BOUNDS = (12, 22, 58, 100)  # top%, bottom%, left%, right%
CURRENT_ZOOM = 3

# Pages to diagnose
DIAGNOSE_PAGES = [0, 1, 3, 7, 15]


def extract_and_save_region(pdf_path, page_no, bounds, zoom):
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

    # Save PNG
    saved_path = OUTPUT_DIR / f"page{page_no}_existing_support_current.png"
    img.save(str(saved_path), format="PNG")

    # Convert to JPEG bytes for API
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    doc.close()

    return buf.getvalue(), str(saved_path)


def call_vision_with_detailed_prompt(image_bytes, region_name="existing_support"):
    """Call Vision API with prompt that returns detailed analysis."""
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    detailed_prompt = """You are looking at what appears to be the existing support section of a Japanese daily report FAX form.

Please analyze this crop and describe what you see:

1. What are the visible item labels/numbers? (e.g., "1.", "2.", "3.", or any text)
2. For each visible item, what text/number is next to it?
3. Are there any printed numbers that are NOT part of handwritten entries? (e.g., row numbers, template numbers)
4. For items you can identify as "1. ネット追加", "2. 電話追加", "3. テレビ追加", what handwritten values are in their right-side entry cells?
5. Are there any bold or emphasized numbers that might be template numbers or row numbers?

Provide raw observation before interpreting as data fields.

Return this JSON:
{
  "visible_items": [{"label": "...", "nearby_text": "...", "type": "label|number|unclear"}],
  "analysis": {
    "item_1_label": "...",
    "item_1_handwritten": "... or null",
    "item_2_label": "...",
    "item_2_handwritten": "... or null",
    "item_3_label": "...",
    "item_3_handwritten": "... or null",
    "suspicious_printed_numbers": "...",
    "conclusion": "..."
  }
}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                {"type": "text", "text": detailed_prompt}
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

    try:
        return json.loads(json_str)
    except:
        return {"raw_response": response_text}


def main():
    print("=" * 80)
    print("Phase 6B: Diagnose HI=40 misread issue")
    print("=" * 80)
    print("\nCurrent bounds: " + str(CURRENT_BOUNDS))
    print("Current zoom: " + str(CURRENT_ZOOM))

    if not PDF_PATH.exists():
        print("\nERROR: PDF not found")
        return

    diagnosis_results = []

    for page_no in DIAGNOSE_PAGES:
        print("\n" + "=" * 80)
        print("Page " + str(page_no))
        print("=" * 80)

        try:
            # Extract region
            img_bytes, saved_path = extract_and_save_region(
                PDF_PATH, page_no,
                CURRENT_BOUNDS,
                CURRENT_ZOOM
            )
            print("Crop saved: " + saved_path)

            # Call Vision API with detailed analysis
            print("Analyzing with Vision API...")
            analysis = call_vision_with_detailed_prompt(img_bytes)

            print("\nAnalysis result:")
            if "analysis" in analysis:
                a = analysis["analysis"]
                print("  Item 1 (ネット追加): " + str(a.get("item_1_handwritten", "?"))[:50])
                print("  Item 2 (電話追加): " + str(a.get("item_2_handwritten", "?"))[:50])
                print("  Item 3 (テレビ追加): " + str(a.get("item_3_handwritten", "?"))[:50])
                print("  Suspicious numbers: " + str(a.get("suspicious_printed_numbers", ""))[:60])
                print("  Conclusion: " + str(a.get("conclusion", ""))[:80])
            elif "raw_response" in analysis:
                print("  Raw: " + str(analysis["raw_response"])[:200])

            diagnosis_results.append({
                "page": page_no,
                "analysis": analysis
            })

        except Exception as e:
            print("ERROR: " + str(e)[:100])
            diagnosis_results.append({
                "page": page_no,
                "error": str(e)[:100]
            })

    # Save diagnosis results
    results_json = OUTPUT_DIR / "diagnosis_results.json"
    with open(results_json, "w", encoding="utf-8") as f:
        json.dump(diagnosis_results, f, ensure_ascii=False, indent=2)
    print("\n" + "=" * 80)
    print("Diagnosis results saved: " + str(results_json))
    print("Crop images saved to: " + str(OUTPUT_DIR))


if __name__ == "__main__":
    main()
