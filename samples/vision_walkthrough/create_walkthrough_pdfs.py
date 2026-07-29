"""
実Vision通しテスト用の完全合成PDF生成スクリプト。
実帳票・実データは一切使用しない。架空の店舗コード・日付・氏名のみ。

【検証記録（2026-07-29、commit 862c8a3の店舗コード抽出修正の実Vision検証時）】
問題：初回のPDF生成では標準フォント"Helvetica"を使用していたが、Helvetica等の
  標準PDFフォント（Type1）は日本語グリフを一切含まない。そのためラベル・値の
  日本語部分がすべて豆腐（黒塗り四角、.notdefグリフ）として描画され、Vision側は
  ASCII値（日付・店舗コード・DataNo・TabNo等）は正しく読めるが、日本語の値
  （氏名・店舗名）は画像上に実質的に存在しないため読み取れない、という状態になっていた。
  fitzで実際に画像化して目視するまで気づかなかった（店舗コード修正自体は正しく
  機能していたため、氏名欄の問題は別の症状として現れた）。
修正：reportlab同梱のCIDフォント（外部フォントファイルのインストール不要）である
  "HeiseiKakuGo-W5"を`pdfmetrics.registerFont(UnicodeCIDFont(...))`で明示登録し、
  日本語を含むすべてのラベル・値に使用するよう変更。
検証結果：修正後、fitzでの再画像化で日本語が正しく描画されることを目視確認した上で、
  実Vision APIを2回実行（ケースA・ケースB）。店舗コード・氏名とも正しく抽出され、
  一致・不一致・要確認の3判定すべてを実データ不使用・完全合成PDFで実証済み
  （ケースCは店舗コード抽出のみの検証のためHelvetica版でも成立していた）。
再検証時の注意：このスクリプトはPDF自体は生成するがgitには含めない
  （.gitignoreによりsamples/**/*.pdf, *.csvは追跡対象外）。再実行するには
  `py -3 samples/vision_walkthrough/create_walkthrough_pdfs.py`。
"""

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont

# Helvetica等の標準PDFフォントは日本語グリフを持たないため、
# 日本語ラベル・値がすべて豆腐（黒塗り四角）で描画され、Visionが読めなくなる。
# reportlab同梱のCIDフォント（外部フォントファイル不要）を明示登録して使う。
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiMin-W3"))
JP_FONT = "HeiseiKakuGo-W5"
JP_FONT_BOLD = "HeiseiKakuGo-W5"  # CIDフォントには太字バリアントがないため同一を使用


def create_form(filename, data, description, include_store_code):
    c = canvas.Canvas(filename, pagesize=A4)
    width, height = A4

    c.setFont(JP_FONT_BOLD, 16)
    c.drawString(20 * mm, height - 20 * mm, "日報帳票")
    c.setFont(JP_FONT, 9)
    c.drawString(20 * mm, height - 25 * mm, description)

    y = height - 35 * mm
    line_height = 10 * mm

    items = [
        ("日付", data["date"]),
        ("店舗名", data["store"]),
        ("氏名", data["name"]),
        ("日報データNo", data["data_no"]),
        ("タブレットNo", data["tab_no"]),
    ]
    if include_store_code:
        items.append(("店舗コード", data["store_code"]))
    items.append(("件数（正の字）", f"{data['count']}"))
    items.append(("合計欄", data["total"]))

    for label, value in items:
        c.setFont(JP_FONT, 11)
        c.drawString(20 * mm, y, f"{label}:")
        c.setFont(JP_FONT_BOLD, 13)
        c.drawString(60 * mm, y, str(value))
        y -= line_height

    c.setFont("Helvetica", 8)
    from datetime import datetime as _dt
    c.drawString(20 * mm, 20 * mm, f"Generated: {_dt.now().strftime('%Y-%m-%d %H:%M:%S')}")

    c.showPage()
    c.save()
    print(f"[OK] {filename} ({description})")


BASE = {
    "date": "2026-05-06",
    "store": "渋谷架空支店",
    "name": "サンプル太郎",
    "data_no": "RPT-2001",
    "tab_no": "TAB-2001",
    "store_code": "DEMO-101",
    "count": 5,
    "total": "12500",
}

# ケースA：一致（店舗コード明記、CSVと全項目一致させる）
create_form(
    "samples/vision_walkthrough/case_a_match.pdf",
    BASE,
    "ケースA：一致",
    include_store_code=True,
)

# ケースB：不一致（店舗コード・日付は同一、氏名だけ変更）
case_b = dict(BASE)
case_b["name"] = "佐藤花子"
create_form(
    "samples/vision_walkthrough/case_b_mismatch.pdf",
    case_b,
    "ケースB：不一致（氏名相違）",
    include_store_code=True,
)

# ケースC：店舗コードなし（店舗名のみ、店舗コード欄自体を記載しない）
create_form(
    "samples/vision_walkthrough/case_c_no_store_code.pdf",
    BASE,
    "ケースC：店舗コードなし",
    include_store_code=False,
)

print("[DONE] 3ケース生成完了")
