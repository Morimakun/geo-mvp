# -*- coding: utf-8 -*-
"""
Phase 2: AI合計欄crop領域の可視化スクリプト

目的:
    PDF full_page 画像に、現在の AI合計欄 crop 領域を赤枠で描画し、
    crop が帳票上のどこを切っているか分かるようにする。

出力:
    - {ページ}_ai_total_region_overlay.png: full_page に赤枠を重ねた画像
    - {ページ}_ai_total_wide_crop.png: AI合計欄周辺を広く切った画像（参考）
"""

import sys
from pathlib import Path

import fitz  # PyMuPDF
from PIL import Image, ImageDraw

if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ============================================================
# 設定
# ============================================================

PDF_PATH = Path("tests/fixtures/geo_pdf_reconciliation/20260529130020168.pdf")
OUTPUT_DIR = Path("data/test_outputs/ai_total_field_mapping_audit")

# AI合計欄を含む case_items 領域（%単位）
# (top%, bottom%, left%, right%)
CASE_ITEMS_BOUNDS = (12, 24, 0, 45)

# wide crop の場合はもっと周辺を含める（±5%）
CASE_ITEMS_BOUNDS_WIDE = (10, 26, -2, 47)  # クリップはしない

FULL_PAGE_ZOOM = 2.5
CROP_ZOOM = 3.0

# 対象ページ
TARGET_PAGES = [
    "P21", "P25", "P27", "P23", "P26", "P19", "P10", "P18", "P22",
    "P2", "P11", "P17", "P24", "P14", "P16", "P30"
]


def page_label_to_index(label: str) -> int:
    """'P10' -> 9 (0-indexed)"""
    return int(label.lstrip("Pp")) - 1


def render_full_page(page: "fitz.Page", zoom: float) -> Image.Image:
    """ページ全体を rendering してPILイメージに変換"""
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def get_crop_bbox(page_rect, bounds, zoom):
    """crop bounds を full_page zoom上の pixel座標に変換"""
    top_pct, bottom_pct, left_pct, right_pct = bounds

    # PDF原典の座標
    left_px = page_rect.width * (left_pct / 100)
    top_px = page_rect.height * (top_pct / 100)
    right_px = page_rect.width * (right_pct / 100)
    bottom_px = page_rect.height * (bottom_pct / 100)

    # zoom適用
    return (
        int(left_px * zoom),
        int(top_px * zoom),
        int(right_px * zoom),
        int(bottom_px * zoom),
    )


def main() -> int:
    if not PDF_PATH.exists():
        print(f"❌ PDF が見つかりません: {PDF_PATH}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(PDF_PATH)
    print(f"PDF読み込み: {PDF_PATH}（総ページ数: {doc.page_count}）")
    print(f"出力先: {OUTPUT_DIR}")
    print(f"AI合計欄bounds: {CASE_ITEMS_BOUNDS} (top%, bottom%, left%, right%)")
    print()

    created = []

    for label in TARGET_PAGES:
        idx = page_label_to_index(label)
        if idx < 0 or idx >= doc.page_count:
            print(f"⚠️ {label}: ページ範囲外（スキップ）")
            continue

        page = doc[idx]
        page_rect = page.rect

        # 1) full_page にcrop枠を描画
        img = render_full_page(page, FULL_PAGE_ZOOM)
        draw = ImageDraw.Draw(img)

        bbox = get_crop_bbox(page_rect, CASE_ITEMS_BOUNDS, FULL_PAGE_ZOOM)
        draw.rectangle(bbox, outline="red", width=3)

        overlay_path = OUTPUT_DIR / f"{label}_ai_total_region_overlay.png"
        img.save(overlay_path)
        created.append(overlay_path.name)

        # 2) wide crop 画像
        wide_crop_pix = page.get_pixmap(
            clip=fitz.Rect(
                page_rect.width * (10 / 100),
                page_rect.height * (10 / 100),
                page_rect.width * (47 / 100),
                page_rect.height * (26 / 100),
            ),
            matrix=fitz.Matrix(CROP_ZOOM, CROP_ZOOM)
        )
        wide_crop_img = Image.frombytes("RGB", (wide_crop_pix.width, wide_crop_pix.height), wide_crop_pix.samples)
        wide_crop_path = OUTPUT_DIR / f"{label}_ai_total_wide_crop.png"
        wide_crop_img.save(wide_crop_path)
        created.append(wide_crop_path.name)

        # 3) current crop 画像（既出だが念のため）
        current_crop_pix = page.get_pixmap(
            clip=fitz.Rect(
                page_rect.width * (CASE_ITEMS_BOUNDS[2] / 100),
                page_rect.height * (CASE_ITEMS_BOUNDS[0] / 100),
                page_rect.width * (CASE_ITEMS_BOUNDS[3] / 100),
                page_rect.height * (CASE_ITEMS_BOUNDS[1] / 100),
            ),
            matrix=fitz.Matrix(CROP_ZOOM, CROP_ZOOM)
        )
        current_crop_path = OUTPUT_DIR / f"{label}_ai_total_current_crop.png"
        current_crop_pix.save(current_crop_path)
        created.append(current_crop_path.name)

        print(f"✅ {label}: overlay / wide_crop / current_crop")

    doc.close()

    print()
    print(f"作成ファイル数: {len(created)}")
    print(f"✅ すべての可視化が完了しました。出力先: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
