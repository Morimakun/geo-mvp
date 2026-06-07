#!/usr/bin/env python3
"""
Direct Vision API test using Anthropic SDK
実Vision APIテストを直接実行
"""

import json
import csv
from pathlib import Path
from datetime import datetime
import base64
import os
import sys
import io

# Imports
try:
    from anthropic import Anthropic
    print("✓ Anthropic SDK imported")
except ImportError:
    print("❌ Anthropic SDK not found")
    print("   Run: pip install anthropic")
    sys.exit(1)

try:
    import fitz  # PyMuPDF
    print("✓ PyMuPDF imported")
except ImportError:
    print("❌ PyMuPDF not found")
    print("   Run: pip install PyMuPDF")
    sys.exit(1)

try:
    from PIL import Image
    print("✓ Pillow imported")
except ImportError:
    print("❌ Pillow not found")
    print("   Run: pip install Pillow")
    sys.exit(1)

PROJECT_ROOT = Path(__file__).parent
PDF_PATH = Path(r"C:\Users\maris\Downloads\20260529130020168.pdf")
OUTPUT_DIR = PROJECT_ROOT / "data/test_outputs"
PROMPT_FILE = OUTPUT_DIR / "improved_ai_prompt_v2.txt"
MODEL_NAME = "claude-sonnet-4-6"

# Test definitions
TEST_PAGES = {
    14: {"index": 13, "store": "イオンモール神戸北", "v3": 34, "user_interp": 3},
    11: {"index": 10, "store": "深江橋", "v3": 20, "user_interp": 2},
    24: {"index": 23, "store": "六甲道", "v3": 7, "user_interp": 2},
    12: {"index": 11, "store": "広畑", "v3": 0, "user_interp": 1},
    28: {"index": 27, "store": "宝殿", "v3": 0, "user_interp": 0},
}

def load_prompt():
    """Load improved prompt"""
    with open(PROMPT_FILE, 'r', encoding='utf-8') as f:
        return f.read()

def extract_page_crop(pdf_path, page_index):
    """Extract page from PDF and crop AI area"""
    pdf = fitz.open(str(pdf_path))
    if page_index >= pdf.page_count:
        raise ValueError(f"Page {page_index} not found")

    page = pdf[page_index]

    # Render at 2x zoom
    mat = fitz.Matrix(2, 2)
    pix = page.get_pixmap(matrix=mat)

    # Convert to PIL Image
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    width, height = img.size

    # Crop AI area (estimated)
    left = int(width * 0.35)
    top = int(height * 0.55)
    right = int(width * 0.50)
    bottom = int(height * 0.70)

    cropped = img.crop((left, top, right, bottom))

    pdf.close()

    return cropped

def image_to_base64(img):
    """Convert PIL Image to base64 PNG"""
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.standard_b64encode(buffer.getvalue()).decode('utf-8')

def call_vision_api(client, image_base64, prompt):
    """Call Vision API with image and prompt"""
    message = client.messages.create(
        model=MODEL_NAME,
        max_tokens=1024,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_base64,
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ],
            }
        ],
    )

    return message.content[0].text

def parse_vision_response(response_text):
    """Parse Vision API response to extract AI value"""
    try:
        # Try to find JSON in response
        if "{" in response_text and "}" in response_text:
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            json_str = response_text[json_start:json_end]
            result = json.loads(json_str)
            return result.get('ai_value'), result.get('confidence', 'unknown'), result.get('interpretation', 'unknown')
    except:
        pass

    # Fallback: try to extract number from response
    import re
    match = re.search(r'ai_value["\']?\s*:\s*([0-9]+|"[^"]*")', response_text)
    if match:
        val = match.group(1).strip('"')
        try:
            return int(val), 'uncertain', 'parsed'
        except:
            return val, 'uncertain', 'parsed'

    return None, 'unknown', 'unparsed'

def normalize_value(value):
    """Normalize Vision API output to integer or None"""
    if value is None or value == "":
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        v = value.strip().lower()

        # Check for blank
        if v in ["blank", "0", "empty", "none", "なし", "空欄"]:
            return 0

        # Check for uncertain
        if v in ["uncertain", "不明", "確認不可"]:
            return None

        # Try to parse as int
        try:
            return int(v)
        except:
            # Try to extract first number
            import re
            match = re.search(r'\d+', v)
            if match:
                return int(match.group())
            return None

    return None

def main():
    print("=" * 100)
    print("Phase 6B AI Tally Prompt V2 - 実Vision APIテスト実行")
    print("=" * 100)
    print()

    # Check files
    if not PDF_PATH.exists():
        print(f"❌ PDF not found: {PDF_PATH}")
        return False

    if not PROMPT_FILE.exists():
        print(f"❌ Prompt file not found: {PROMPT_FILE}")
        return False

    print(f"✓ PDF found: {PDF_PATH.name}")
    print(f"✓ Prompt file loaded: {PROMPT_FILE.name}")
    print()

    # Load prompt
    prompt = load_prompt()

    # Check APIキー
    if not os.getenv("ANTHROPIC_API_KEY"):
        print("❌ APIキー未設定")
        print("   環境変数 ANTHROPIC_API_KEY を設定してください")
        return False

    # Initialize Anthropic client
    client = Anthropic()
    print(f"✓ Anthropic client initialized")
    print(f"✓ Using model: {MODEL_NAME}")
    print()

    results = []

    print("=" * 100)
    print("Vision APIテスト実行中...")
    print("=" * 100)
    print()

    for page_no, page_info in TEST_PAGES.items():
        page_idx = page_info['index']
        store = page_info['store']
        v3 = page_info['v3']
        user_interp = page_info['user_interp']

        print(f"【P{page_no}】{store}")
        print(f"  v3={v3}, user_interpretation={user_interp}")

        try:
            # Extract and crop
            print(f"  → Extracting page {page_idx}...", end=" ", flush=True)
            ai_crop = extract_page_crop(PDF_PATH, page_idx)
            print(f"✓ ({ai_crop.width}x{ai_crop.height})")

            # Convert to base64
            print(f"  → Encoding image...", end=" ", flush=True)
            img_b64 = image_to_base64(ai_crop)
            print(f"✓")

            # Call Vision API
            print(f"  → Calling Vision API...", end=" ", flush=True)
            response = call_vision_api(client, img_b64, prompt)
            print(f"✓")

            # Parse response
            ai_val_raw, confidence, interpretation = parse_vision_response(response)
            v2_actual = normalize_value(ai_val_raw)

            # Judge
            is_correct = v2_actual == user_interp
            status_icon = "✅" if is_correct else "❌" if v2_actual is not None else "⚠️"

            print(f"  → V2実測値: {v2_actual} {status_icon}")
            if not is_correct and v2_actual is not None:
                print(f"     期待値: {user_interp}")
            print()

            results.append({
                'page_no': page_no,
                'page_index': page_idx,
                'store_name': store,
                'v3_value': v3,
                'user_interpretation': user_interp,
                'v2_actual_value': v2_actual,
                'v2_confidence': confidence,
                'v2_interpretation': interpretation,
                'match_v3': "✓" if v2_actual == v3 else "✗",
                'match_user': "✓" if v2_actual == user_interp else "✗",
                'status': 'correct' if is_correct else ('mismatch' if v2_actual is not None else 'error'),
                'raw_response': response[:200]
            })

        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            results.append({
                'page_no': page_no,
                'page_index': page_idx,
                'store_name': store,
                'v3_value': v3,
                'user_interpretation': user_interp,
                'v2_actual_value': None,
                'v2_confidence': 'error',
                'v2_interpretation': 'error',
                'match_v3': '?',
                'match_user': '?',
                'status': 'error',
                'raw_response': str(e)[:200]
            })
            print()

    # Save CSV
    print("=" * 100)
    print("結果を保存中...")
    print("=" * 100)
    print()

    csv_path = OUTPUT_DIR / "phase6b_ai_tally_prompt_v2_actual_result.csv"

    fieldnames = [
        'page_no', 'page_index', 'store_name',
        'v3_value', 'user_interpretation', 'v2_actual_value',
        'v2_confidence', 'v2_interpretation',
        'match_v3', 'match_user', 'status'
    ]

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            # Extract only fields that are in fieldnames
            safe_row = {key: r.get(key, "") for key in fieldnames}
            writer.writerow(safe_row)

    print(f"✓ CSV saved: {csv_path.name}")

    # Generate Markdown
    success_count = sum(1 for r in results if r['status'] == 'correct')
    total = len(results)

    md_content = f"""# Phase 6B AI Tally Prompt V2 - 実Vision APIテスト結果

**テスト実施日：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**テスト方式：** 実Vision API呼び出し
**対象：** 5ページ（P14, P11, P24, P12, P28）のAI合計欄のみ

---

## テスト結果サマリー

### V2実測成功率

**{success_count}/5 = {success_count*20:.0f}%**

---

## ページ別結果

| ページ | v3値 | V2実測値 | ユーザー目視解釈 | 判定 |
|--------|------|---------|-----------------|------|
"""

    for result in results:
        page_no = result['page_no']
        v3 = result['v3_value']
        v2 = result['v2_actual_value']
        user = result['user_interpretation']
        status = "✅" if result['status'] == 'correct' else ("❌" if result['status'] == 'mismatch' else "⚠️")
        md_content += f"| P{page_no} | {v3} | {v2} | {user} | {status} |\n"

    md_content += f"""

---

## 詳細分析

### 誤読消滅の確認

"""

    p14 = next((r for r in results if r['page_no'] == 14), None)
    p11 = next((r for r in results if r['page_no'] == 11), None)
    p24 = next((r for r in results if r['page_no'] == 24), None)
    p12 = next((r for r in results if r['page_no'] == 12), None)
    p28 = next((r for r in results if r['page_no'] == 28), None)

    if p14:
        if p14['v2_actual_value'] is not None and p14['v2_actual_value'] != 34:
            md_content += f"✅ **P14：34誤読が消えた** - V2実測値={p14['v2_actual_value']}\n"
        elif p14['v2_actual_value'] == 34:
            md_content += f"❌ **P14：34誤読が残存** - V2実測値={p14['v2_actual_value']}\n"
        else:
            md_content += f"⚠️ **P14：読取失敗**\n"

    if p11:
        if p11['v2_actual_value'] is not None and p11['v2_actual_value'] != 20:
            md_content += f"✅ **P11：20誤読が消えた** - V2実測値={p11['v2_actual_value']}\n"
        elif p11['v2_actual_value'] == 20:
            md_content += f"❌ **P11：20誤読が残存** - V2実測値={p11['v2_actual_value']}\n"
        else:
            md_content += f"⚠️ **P11：読取失敗**\n"

    if p24:
        if p24['v2_actual_value'] is not None and p24['v2_actual_value'] != 7:
            md_content += f"✅ **P24：7誤読が消えた** - V2実測値={p24['v2_actual_value']}\n"
        elif p24['v2_actual_value'] == 7:
            md_content += f"❌ **P24：7誤読が残存** - V2実測値={p24['v2_actual_value']}\n"
        else:
            md_content += f"⚠️ **P24：読取失敗**\n"

    md_content += f"""

### P28維持確認

"""

    if p28:
        if p28['v2_actual_value'] == 0:
            md_content += f"✅ **P28：0を維持** - V2実測値={p28['v2_actual_value']}\n"
        elif p28['v2_actual_value'] is not None:
            md_content += f"⚠️ **P28：値が変化** - V2実測値={p28['v2_actual_value']}（期待：0）\n"
        else:
            md_content += f"⚠️ **P28：読取失敗**\n"

    md_content += f"""

---

## 全30ページ展開への判定

### 成功基準チェック

| 基準 | 結果 |
|------|------|
| 5ページ中4以上正解 | {'✅ 達成' if success_count >= 4 else '❌ 未達'} ({success_count}/5) |
| 34/20/7誤読が消える | {'✅ 確認' if (p14 and p14['v2_actual_value'] not in [None, 34]) and (p11 and p11['v2_actual_value'] not in [None, 20]) and (p24 and p24['v2_actual_value'] not in [None, 7]) else '⚠️ 要確認'} |
| P28=0を維持 | {'✅ 達成' if p28 and p28['v2_actual_value'] == 0 else '⚠️'} |

### 判定

"""

    if success_count >= 4:
        md_content += f"""
**✅ 全30ページへ展開推奨**

根拠：
- V2実測成功率：{success_count}/5 = {success_count*20:.0f}%
- 成功基準達成

次のステップ：
1. extractor.py に改善プロンプトを反映
2. 全30ページで再抽出実施
3. AI FLAG 13件の削減効果を検証
"""
    else:
        md_content += f"""
**⚠️ 追加検証が必要**

根拠：
- V2実測成功率：{success_count}/5 = {success_count*20:.0f}%
- 成功基準未達

検討事項：
- 失敗ページの原因分析
- プロンプト改善の必要性
- クロップ位置調整の検討
"""

    md_content += f"""

---

## ページ別詳細

"""

    for result in results:
        page_no = result['page_no']
        store = result['store_name']
        v3 = result['v3_value']
        v2 = result['v2_actual_value']
        user = result['user_interpretation']

        md_content += f"""
### P{page_no} {store}

| 項目 | 値 |
|------|-----|
| v3値 | {v3} |
| V2実測値 | {v2} |
| ユーザー目視解釈 | {user} |
| 判定 | {'✅ 正解' if result['status'] == 'correct' else '❌ 不一致' if result['status'] == 'mismatch' else '⚠️ エラー'} |

"""

    md_content += """---

**テスト状態：** ✅ 実Vision APIテスト完了
**実測結果：** V2実測値取得済み
"""

    md_path = PROJECT_ROOT / "docs/PHASE_6B_AI_TALLY_PROMPT_V2_ACTUAL_RESULT.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"✓ Markdown saved: {md_path.name}")
    print()

    # Summary
    print("=" * 100)
    print("✅ 実Vision APIテスト完了")
    print("=" * 100)
    print()
    print(f"V2実測成功率：{success_count}/5 = {success_count*20:.0f}%")
    print()
    print("出力ファイル：")
    print(f"  1. {csv_path}")
    print(f"  2. {md_path}")
    print()

    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ エラー：{e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
