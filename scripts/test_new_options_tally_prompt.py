"""
Test new_options tally mark prompt on Pages 0, 3, 7, 12.

Expected values (from visual analysis):
  Page 0: GS=1, GT=null, GU=1 (Row5=1, Row6=2)
  Page 3: GS=2 (T-shape = tally 2), GT=null, GU=null (Row9=2)
  Page 7: GS=uncertain or null (0-like mark), GT=null, GU=null
  Page 12: GS=null, GT=null, GU=null (all empty)
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
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "test_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

TEST_PAGES = [0, 3, 7, 12]

BOUNDS = (18, 50, 38, 62)
ZOOM = 4

# Updated tally mark prompt
TALLY_PROMPT = """あなたは日報FAX帳票の【新規オプション等】の領域を見ています。

この表には番号付きの項目が並んでいます。上から順に：
- 「1. eo光電話」の数値 → GS として返す
- 「2. 地デジBS」の数値 → GT として返す
- 「3. CS」の数値 → GU として返す

【前提】この欄の手書き記入は、基本的に「正の字カウント」です。
アラビア数字ではなく、正の字（画数で数を表す）として読み取ってください。

【正の字カウントの読み取り方】:

- 空欄（何も書かれていない） → null
- 横線1本（「一」の形） → 1
- T字形・7字形・横線＋縦線に見える形 → 2（正の字の2画目）
- 3画分に見える形 → 3
- 4画分に見える形 → 4
- 完成した「正」の字 → 5

**重要**: T字形や7字形に見えるものは、アルファベットや数字ではなく、
正の字の途中形（2画目まで）として扱ってください。

【注意事項】:
- テンプレート印字文字や罫線は、値として読まないでください
- 罫線と完全に重なって判読不能な場合 → "uncertain"
- 正の字か別の記入か判断がつかない場合 → "uncertain"
- 空欄は null です（0 ではありません）

必ず以下のJSON形式で返してください：
{
  "GS": 数値または"uncertain"またはnull,
  "GT": 数値または"uncertain"またはnull,
  "GU": 数値または"uncertain"またはnull
}
"""

EXPECTED = {
    0: {"GS": 1, "GT": None, "GU": 1, "note": "GS=1 (horizontal line), GU=1 (horizontal line)"},
    3: {"GS": 2, "GT": None, "GU": None, "note": "GS=2 (T-shape = tally 2画目)"},
    7: {"GS": "uncertain_or_null", "GT": None, "GU": None, "note": "GS has 0-like mark, not tally"},
    12: {"GS": None, "GT": None, "GU": None, "note": "All empty"},
}


def extract_region_image(pdf_path, page_no, bounds, zoom):
    doc = fitz.open(str(pdf_path))
    page = doc[page_no]
    rect = page.rect
    top_pct, bottom_pct, left_pct, right_pct = bounds
    region_rect = fitz.Rect(
        rect.width * (left_pct / 100), rect.height * (top_pct / 100),
        rect.width * (right_pct / 100), rect.height * (bottom_pct / 100)
    )
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(clip=region_rect, matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    doc.close()
    return buf.getvalue()


def call_vision_api(image_bytes, prompt):
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    for attempt in range(3):
        try:
            message = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=512,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
                    {"type": "text", "text": prompt}
                ]}],
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
                time.sleep(10 * (attempt + 1))
            elif attempt < 2:
                time.sleep(2)
            else:
                return {"error": str(e)[:100]}
    return {"error": "max retries exceeded"}


def main():
    print("=" * 80)
    print("Test new_options tally mark prompt")
    print("=" * 80)

    results = []

    for page_no in TEST_PAGES:
        print(f"\n--- Page {page_no} ---")
        expected = EXPECTED[page_no]
        print(f"  Expected: GS={expected['GS']}, GT={expected['GT']}, GU={expected['GU']}")
        print(f"  Note: {expected['note']}")

        img_bytes = extract_region_image(PDF_PATH, page_no, BOUNDS, ZOOM)
        result = call_vision_api(img_bytes, TALLY_PROMPT)

        gs = result.get("GS")
        gt = result.get("GT")
        gu = result.get("GU")

        print(f"  Actual:   GS={gs}, GT={gt}, GU={gu}")

        # Check against expected
        checks = []
        exp_gs = expected["GS"]
        if exp_gs == "uncertain_or_null":
            ok_gs = gs is None or gs == "uncertain"
            checks.append(f"GS: {'PASS' if ok_gs else 'FAIL'} (expected null/uncertain, got {gs})")
        elif exp_gs is None:
            ok_gs = gs is None
            checks.append(f"GS: {'PASS' if ok_gs else 'FAIL'} (expected null, got {gs})")
        else:
            ok_gs = gs == exp_gs
            checks.append(f"GS: {'PASS' if ok_gs else 'FAIL'} (expected {exp_gs}, got {gs})")

        exp_gt = expected["GT"]
        ok_gt = gt is None or gt == exp_gt
        checks.append(f"GT: {'PASS' if ok_gt else 'FAIL'} (expected {exp_gt}, got {gt})")

        exp_gu = expected["GU"]
        if exp_gu is None:
            ok_gu = gu is None
        else:
            ok_gu = gu == exp_gu
        checks.append(f"GU: {'PASS' if ok_gu else 'FAIL'} (expected {exp_gu}, got {gu})")

        for c in checks:
            print(f"  {c}")

        results.append({
            "page": page_no,
            "GS_expected": str(exp_gs),
            "GS_actual": gs,
            "GT_expected": str(exp_gt),
            "GT_actual": gt,
            "GU_expected": str(exp_gu),
            "GU_actual": gu,
            "note": expected["note"],
        })

        time.sleep(0.5)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"\n{'Page':>6} | {'GS exp':>10} | {'GS act':>10} | {'GT exp':>10} | {'GT act':>10} | {'GU exp':>10} | {'GU act':>10}")
    print("-" * 80)
    for r in results:
        print(f"{r['page']:>6} | {str(r['GS_expected']):>10} | {str(r['GS_actual']):>10} | {str(r['GT_expected']):>10} | {str(r['GT_actual']):>10} | {str(r['GU_expected']):>10} | {str(r['GU_actual']):>10}")

    # Save
    json_path = OUTPUT_DIR / "phase6b_new_options_tally_test.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nSaved: {json_path.name}")


if __name__ == "__main__":
    main()
