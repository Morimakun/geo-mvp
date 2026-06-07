#!/usr/bin/env python3
"""
Phase 6B AI Tally Prompt V2.1 - High Resolution Test
高解像度画像でのVision API テスト準備
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
    sys.exit(1)

try:
    import fitz  # PyMuPDF
    print("✓ PyMuPDF imported")
except ImportError:
    print("❌ PyMuPDF not found")
    sys.exit(1)

try:
    from PIL import Image
    print("✓ Pillow imported")
except ImportError:
    print("❌ Pillow not found")
    sys.exit(1)

# Constants
PROJECT_ROOT = Path(__file__).parent.parent
PDF_PATH = Path(r"C:\Users\maris\Downloads\20260529130020168.pdf")
OUTPUT_DIR = PROJECT_ROOT / "data/test_outputs"
CROPS_DIR = OUTPUT_DIR / "phase6b_ai_tally_v21_crops"
PROMPT_FILE = OUTPUT_DIR / "improved_ai_prompt_v2.txt"
MODEL_NAME = "claude-sonnet-4-6"

# Create crops directory if not exists
CROPS_DIR.mkdir(parents=True, exist_ok=True)

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

def extract_highres_crops(pdf_path, page_index, dpi_scale=4):
    """
    Extract page from PDF with high resolution.

    Args:
        pdf_path: Path to PDF
        page_index: Page index (0-based)
        dpi_scale: Scale factor (2=print DPI, 4=300dpi equivalent, 5=400dpi equivalent)

    Returns:
        tuple: (ai_crop, context_crop) - PIL Images
    """
    pdf = fitz.open(str(pdf_path))
    if page_index >= pdf.page_count:
        raise ValueError(f"Page {page_index} not found")

    page = pdf[page_index]

    # Render at high DPI
    mat = fitz.Matrix(dpi_scale, dpi_scale)
    pix = page.get_pixmap(matrix=mat)

    # Convert to PIL Image
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    width, height = img.size

    # Pattern A: AI area only (tight crop)
    left_a = int(width * 0.35)
    top_a = int(height * 0.55)
    right_a = int(width * 0.50)
    bottom_a = int(height * 0.70)
    ai_crop = img.crop((left_a, top_a, right_a, bottom_a))

    # Pattern B: AI row with context (AU/AV/AY/AZ/AI + labels)
    left_b = int(width * 0.10)  # Wider left margin for labels
    top_b = int(height * 0.50)  # Start a bit higher to include row label
    right_b = int(width * 0.55)  # Include a bit of right margin
    bottom_b = int(height * 0.75)  # Include a bit below
    context_crop = img.crop((left_b, top_b, right_b, bottom_b))

    pdf.close()

    return ai_crop, context_crop

def image_to_base64(img):
    """Convert PIL Image to base64 PNG"""
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.standard_b64encode(buffer.getvalue()).decode('utf-8')

def normalize_value(value):
    """Normalize Vision API output to integer or None"""
    if value is None or value == "":
        return None

    if isinstance(value, int):
        return value

    if isinstance(value, str):
        v = value.strip().lower()

        # Check for blank/empty/none
        if v in ["blank", "0", "empty", "none", "なし", "空欄"]:
            return 0

        # Check for uncertain/cannot read
        if v in ["uncertain", "不明", "確認不可", "none", "null"]:
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
    print("Phase 6B AI Tally Prompt V2.1 - 高解像度テスト準備")
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
    print(f"✓ Prompt file found: {PROMPT_FILE.name}")
    print(f"✓ Using DPI scale: 4 (≈300dpi)")
    print(f"✓ Crops will be saved to: {CROPS_DIR.name}")
    print()

    # Load prompt
    prompt = load_prompt()

    results = []

    print("=" * 100)
    print("高解像度 Crop 画像生成中...")
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
            # Extract high-res crops
            print(f"  → Extracting high-res crops...", end=" ", flush=True)
            ai_crop, context_crop = extract_highres_crops(PDF_PATH, page_idx, dpi_scale=4)
            print(f"✓ (AI: {ai_crop.width}×{ai_crop.height}, Context: {context_crop.width}×{context_crop.height})")

            # Save crop images
            print(f"  → Saving crop images...", end=" ", flush=True)
            ai_crop_path = CROPS_DIR / f"P{page_no}_ai_highres.png"
            context_crop_path = CROPS_DIR / f"P{page_no}_ai_context_highres.png"
            ai_crop.save(ai_crop_path)
            context_crop.save(context_crop_path)
            print(f"✓")

            # Record results
            results.append({
                'page_no': page_no,
                'page_index': page_idx,
                'store_name': store,
                'v3_value': v3,
                'user_interpretation': user_interp,
                'ai_crop_path': str(ai_crop_path.relative_to(PROJECT_ROOT)),
                'ai_crop_size': f"{ai_crop.width}x{ai_crop.height}",
                'context_crop_path': str(context_crop_path.relative_to(PROJECT_ROOT)),
                'context_crop_size': f"{context_crop.width}x{context_crop.height}",
                'status': 'crop_saved',
                'note': 'Vision API 呼び出し待機中'
            })

            print()

        except Exception as e:
            print(f"  ❌ Error: {str(e)}")
            results.append({
                'page_no': page_no,
                'page_index': page_idx,
                'store_name': store,
                'v3_value': v3,
                'user_interpretation': user_interp,
                'ai_crop_path': 'ERROR',
                'ai_crop_size': 'ERROR',
                'context_crop_path': 'ERROR',
                'context_crop_size': 'ERROR',
                'status': 'error',
                'note': str(e)[:100]
            })
            print()

    # Save CSV
    print("=" * 100)
    print("Crop 生成結果を保存中...")
    print("=" * 100)
    print()

    csv_path = OUTPUT_DIR / "phase6b_ai_tally_prompt_v21_highres_crop_status.csv"

    fieldnames = [
        'page_no', 'page_index', 'store_name',
        'v3_value', 'user_interpretation',
        'ai_crop_path', 'ai_crop_size',
        'context_crop_path', 'context_crop_size',
        'status', 'note'
    ]

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            safe_row = {key: r.get(key, "") for key in fieldnames}
            writer.writerow(safe_row)

    print(f"✓ CSV saved: {csv_path.name}")
    print()

    # Generate status report
    success_count = sum(1 for r in results if r['status'] == 'crop_saved')
    total = len(results)

    md_content = f"""# Phase 6B AI Tally Prompt V2.1 - 高解像度Crop生成結果

**生成日時：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**目的：** V2失敗（0/5）の原因分析・改善準備
**DPI設定：** 4倍スケール（≈300dpi）
**Crop パターン：**
- パターンA：AI欄単体（高解像度）
- パターンB：AU/AV/AY/AZ/AI含む（文脈付き高解像度）

---

## 生成結果サマリー

### Crop生成成功率

**{success_count}/{total} = {success_count*100//total if total > 0 else 0}%**

---

## ページ別結果

| ページ | 店舗名 | パターンA | パターンB | 状態 |
|--------|--------|-----------|-----------|------|
"""

    for result in results:
        page_no = result['page_no']
        store = result['store_name']
        status_icon = "✓" if result['status'] == 'crop_saved' else "✗"
        ai_size = result['ai_crop_size']
        ctx_size = result['context_crop_size']

        md_content += f"| P{page_no} | {store} | {ai_size} | {ctx_size} | {status_icon} |\n"

    md_content += f"""

---

## V2.1テスト方針

### 背景：V2の失敗原因

V2実測テストは **0/5 完全失敗** しました。原因分析：

| 問題 | 詳細 |
|------|------|
| **入力画像の低解像度** | V2では 179×252px という極小サイズで Vision に投げていた |
| **Crop範囲が狭すぎる** | AI欄だけを切り出しており、行ラベルや周辺文脈が完全に失われている |
| **プロンプト仕様が厳しい** | P11/P24/P28 が None（判定不能）に逃げている |

### V2.1の改善内容

1. **高解像度レンダリング**
   - 4倍スケール（≈300dpi）でPDFを再レンダリング
   - 手書き正の字が視認可能なサイズに

2. **2種類のCrop パターン**
   - **パターンA（AI欄単体）**：AI合計欄のみ（高解像度版）
   - **パターンB（文脈付き）**：AU/AV/AY/AZ/AI行全体 + ラベル
   - 目的：Vision が「どのセルを読むべきか」判断しやすくする

3. **Vision API再試行**
   - パターンA と B の両方で試し、どちらが効果的かを比較
   - raw_response を必ず保存（失敗原因の事後分析用）

---

## Crop生成結果詳細

"""

    for result in results:
        page_no = result['page_no']
        store = result['store_name']

        md_content += f"""### P{page_no} {store}

- **パターンA（AI欄単体）**
  - サイズ：{result['ai_crop_size']}
  - ファイル：`{result['ai_crop_path']}`

- **パターンB（文脈付き）**
  - サイズ：{result['context_crop_size']}
  - ファイル：`{result['context_crop_path']}`

"""

    md_content += f"""

---

## 次のステップ

### 今回（完了）
- ✅ 高解像度 Crop 画像生成
- ✅ 2種類パターンの保存
- ⏸️ Vision API 呼び出しは **今回は実行しない**

### 次回
- Vision API 呼び出し実行
- パターンA vs B の比較検証
- V2.1の成功/失敗判定
- 必要に応じて V2.2 検討

---

**状態：** Crop生成完了・Vision API呼び出し待機中
**スクリプト：** `scripts/test_ai_tally_prompt_v21_highres.py`
**実行予定：** 画像確認後、Vision API再実行
"""

    md_path = PROJECT_ROOT / "docs/PHASE_6B_AI_TALLY_PROMPT_V21_HIGHRES_STATUS.md"
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_content)

    print(f"✓ Status report saved: {md_path.name}")
    print()

    # Summary
    print("=" * 100)
    print("Crop生成完了")
    print("=" * 100)
    print()
    print(f"生成成功率：{success_count}/{total} = {success_count*100//total if total > 0 else 0}%")
    print()
    print("保存ファイル：")
    print(f"  CSV:      {csv_path}")
    print(f"  Report:   {md_path}")
    print(f"  Crops:    {CROPS_DIR}")
    print()
    print("⏸️  Vision API 呼び出しは次回実行")
    print()

    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
