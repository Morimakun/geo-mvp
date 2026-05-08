"""
サンプル帳票PDFの生成スクリプト
複数パターンのテスト用帳票を作成します
"""

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from datetime import datetime

def create_sample_forms():
    """3つのパターンの帳票PDFを作成"""

    # パターン1: 完全一致
    create_form(
        filename="samples/form_001_match.pdf",
        data={
            "date": "2026-05-06",
            "store": "渋谷店",
            "name": "田中太郎",
            "data_no": "001",
            "tab_no": "AB-01",
            "count_text": "●●●●● (5本)",
            "count_num": 5,
            "total": "12500",
        },
        description="パターン1：完全一致"
    )

    # パターン2: 件数ズレ（不一致）
    create_form(
        filename="samples/form_002_mismatch.pdf",
        data={
            "date": "2026-05-06",
            "store": "新宿店",
            "name": "山田花子",
            "data_no": "002",
            "tab_no": "AB-02",
            "count_text": "●●●●●● (6本)",
            "count_num": 6,
            "total": "15000",
        },
        description="パターン2：件数ズレ（帳票=6、CSV=5 → 不一致）"
    )

    # パターン3: 正の字が不鮮明（要確認）
    create_form(
        filename="samples/form_003_pending.pdf",
        data={
            "date": "2026-05-06",
            "store": "池袋店",
            "name": "佐藤次郎",
            "data_no": "",  # 空欄
            "tab_no": "CD-03",
            "count_text": "●●●? (3本か4本か不鮮明)",
            "count_num": None,  # 読取失敗想定
            "total": "7500",
        },
        description="パターン3：正の字が不鮮明、DataNo空欄 → 要確認"
    )


def create_form(filename, data, description):
    """
    帳票PDFを生成

    Args:
        filename: 出力ファイル名
        data: 帳票データ
        description: 説明（デバッグ用）
    """
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    # ===== タイトル =====
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20*mm, height - 20*mm, "日報帳票")
    c.setFont("Helvetica", 9)
    c.drawString(20*mm, height - 25*mm, description)

    y = height - 35*mm

    # ===== 帳票項目 =====
    c.setFont("Helvetica", 10)
    line_height = 8*mm

    items = [
        ("日付", data.get("date", "")),
        ("店舗名", data.get("store", "")),
        ("氏名", data.get("name", "")),
        ("日報データNo", data.get("data_no", "(空欄)")),
        ("タブレットNo", data.get("tab_no", "")),
        ("件数（正の字）", data.get("count_text", "")),
        ("合計欄", data.get("total", "")),
    ]

    for label, value in items:
        c.drawString(20*mm, y, f"{label}:")
        c.drawString(60*mm, y, str(value))
        y -= line_height

    # ===== 下部 =====
    c.setFont("Helvetica", 8)
    c.drawString(20*mm, 20*mm, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    c.save()
    print(f"[OK] {filename} を作成しました")


if __name__ == "__main__":
    create_sample_forms()
    print("\n[DONE] 全サンプル帳票を作成完了")
