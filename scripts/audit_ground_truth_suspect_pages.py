# -*- coding: utf-8 -*-
"""
Phase 1: PDF目視正解データ監査用 crop 画像作成スクリプト

目的:
    PDF目視正解候補と v3/V2.2/CSV が食い違うページについて、
    AI合計欄の crop 画像と full page 画像を作成し、
    人間が再目視確認できる状態にする。

重要:
    - PyMuPDF のみ使用（Vision API なし / OCR なし / 再抽出なし）
    - 既存の evaluate_phase6b_30pages_v3.py の case_items bounds を参考
    - 誤った crop を出すより full_page を必ず併産する

使い方:
    python scripts/audit_ground_truth_suspect_pages.py
"""

import sys
from pathlib import Path

import fitz  # PyMuPDF

# Windows コンソールでの UTF-8 出力
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# ============================================================
# 設定
# ============================================================

PDF_PATH = Path("tests/fixtures/geo_pdf_reconciliation/20260529130020168.pdf")
OUTPUT_DIR = Path("data/test_outputs/ground_truth_audit_v2")

# AI合計欄を含む case_items 領域
# evaluate_phase6b_30pages_v3.py の REGIONS["case_items"] と同一 bounds
# (top%, bottom%, left%, right%)
CASE_ITEMS_BOUNDS = (12, 24, 0, 45)
CROP_ZOOM = 3.0
FULL_PAGE_ZOOM = 2.5

# 優先監査ページ（複数ソース一致なのに目視正解候補と食い違う疑い）
SUSPECT_PAGES = ["P10", "P18", "P19", "P21", "P22", "P23", "P25", "P26", "P27"]

# 比較用の真失敗候補ページ（AI抽出側の失敗・crop混入などの疑い）
FAILURE_CANDIDATE_PAGES = ["P2", "P11", "P14", "P17", "P24"]

ALL_TARGET_PAGES = SUSPECT_PAGES + FAILURE_CANDIDATE_PAGES


def page_label_to_index(label: str) -> int:
    """'P10' -> 9 (0-indexed)"""
    return int(label.lstrip("Pp")) - 1


def render_crop(page: "fitz.Page", bounds, zoom: float) -> "fitz.Pixmap":
    """ページの指定割合領域を高解像度で rendering する"""
    top_pct, bottom_pct, left_pct, right_pct = bounds
    rect = page.rect
    clip = fitz.Rect(
        rect.width * (left_pct / 100),
        rect.height * (top_pct / 100),
        rect.width * (right_pct / 100),
        rect.height * (bottom_pct / 100),
    )
    mat = fitz.Matrix(zoom, zoom)
    return page.get_pixmap(clip=clip, matrix=mat)


def main() -> int:
    if not PDF_PATH.exists():
        print(f"❌ PDF が見つかりません: {PDF_PATH}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(PDF_PATH)
    print(f"PDF読み込み: {PDF_PATH}（総ページ数: {doc.page_count}）")
    print(f"出力先: {OUTPUT_DIR}")
    print()

    created = []

    for label in ALL_TARGET_PAGES:
        idx = page_label_to_index(label)
        if idx < 0 or idx >= doc.page_count:
            print(f"⚠️ {label}: ページ範囲外（スキップ）")
            continue

        page = doc[idx]

        # 1) AI合計欄を含む case_items crop（zoom 3.0）
        crop_pix = render_crop(page, CASE_ITEMS_BOUNDS, CROP_ZOOM)
        crop_path = OUTPUT_DIR / f"{label}_ai_total_crop.png"
        crop_pix.save(crop_path)
        created.append(crop_path.name)

        # 2) full page（zoom 2.5）— crop 位置ズレ時の保険
        full_pix = page.get_pixmap(matrix=fitz.Matrix(FULL_PAGE_ZOOM, FULL_PAGE_ZOOM))
        full_path = OUTPUT_DIR / f"{label}_full_page.png"
        full_pix.save(full_path)
        created.append(full_path.name)

        kind = "優先監査" if label in SUSPECT_PAGES else "真失敗候補"
        print(f"✅ {label} ({kind}): crop {crop_pix.width}x{crop_pix.height} / full {full_pix.width}x{full_pix.height}")

    doc.close()

    print()
    print(f"作成ファイル数: {len(created)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
