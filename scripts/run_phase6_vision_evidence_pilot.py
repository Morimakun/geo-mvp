"""Phase 6 Step 3B: 実画像Vision抽出パイロット実行スクリプト（v2 / region-scoped）。

src/phase6/vision_evidence_client.py を呼び出すだけの一時実行スクリプト。
ロジックはすべてsrc側に置き、このファイルは実行順序の制御と結果表示のみを行う。

v1パイロット（run_id=step3b_pilot_v1）の結果は上書きしない。このスクリプトは
新しいrun_idで別ディレクトリに出力する。

実行順序（ユーザー指示）:
    1. contact sheetを生成する（Vision APIへは渡さない。目視確認用）。
    2. P59だけを先に実行し、契約どおりに通ることを確認する。
    3. P59が成功した場合のみ、P32・P41・P66を実行する。
    期待値と異なるという理由だけでの追加再試行はしない（結果が違えばそのまま記録する）。

対象はこの4ページのみ（66ページ一括処理はしない）。
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402
from anthropic import Anthropic  # noqa: E402

from src.phase6.vision_evidence_client import (  # noqa: E402
    SOURCE_PDF_FILENAME,
    SOURCE_PDF_SHA256,
    build_contact_sheet,
    verify_source_pdf,
    run_vision_evidence_pilot_page,
)

RUN_ID = "step3b_pilot_v2"
OUTPUT_DIR = REPO_ROOT / "outputs" / "phase6_vision_evidence_pilot"

TARGET_PAGES = [
    {"pdf_page_no": 32, "form_version": "new", "selected_business_date": date(2026, 6, 26)},
    {"pdf_page_no": 41, "form_version": "new", "selected_business_date": date(2026, 6, 26)},
    {"pdf_page_no": 59, "form_version": "new", "selected_business_date": date(2026, 6, 25)},
    {"pdf_page_no": 66, "form_version": "old", "selected_business_date": date(2026, 6, 25)},
]


def _run_page(client: Anthropic, spec: dict) -> dict:
    print(f"--- P{spec['pdf_page_no']} 実行中 (run_id={RUN_ID}, form_version={spec['form_version']}, "
          f"selected_business_date={spec['selected_business_date'].isoformat()}) ---")
    audit = run_vision_evidence_pilot_page(
        client,
        run_id=RUN_ID,
        pdf_page_no=spec["pdf_page_no"],
        expected_form_version=spec["form_version"],
        selected_business_date=spec["selected_business_date"],
        output_dir=OUTPUT_DIR,
    )
    print(f"  success={audit['success']} attempt_count={audit['attempt_count']}")
    for a in audit["attempts"]:
        print(f"    attempt#{a['attempt_number']}: success={a['success']} "
              f"error_type={a['error_type']} stop_reason={a['stop_reason']} "
              f"in={a['input_tokens']} out={a['output_tokens']}")
    if audit["success"]:
        pe = audit["page_evidence"]
        print(f"  store_code={pe['store_code_evidence']['raw_value']!r} "
              f"status={pe['store_code_evidence']['status']}")
        print(f"  intro_total={pe['intro_total']} "
              f"intro_tally_status={pe['intro_evidence']['tally']['observation_status']} "
              f"intro_tally_count={pe['intro_evidence']['tally']['tally_count']}")
        print(f"  voice_total={pe['voice_callout_total']} "
              f"voice_tally_status={pe['voice_evidence']['tally']['observation_status']} "
              f"voice_tally_count={pe['voice_evidence']['tally']['tally_count']}")
    return audit


def main() -> int:
    print(f"元PDF: {SOURCE_PDF_FILENAME}")
    print(f"元PDF SHA-256: {SOURCE_PDF_SHA256}")
    verify_source_pdf()
    print("プリフライト確認OK。")

    contact_sheet_path = OUTPUT_DIR / RUN_ID / "contact_sheet.jpg"
    build_contact_sheet(
        [{"pdf_page_no": p["pdf_page_no"], "form_version": p["form_version"]} for p in TARGET_PAGES],
        output_path=contact_sheet_path,
        thumb_scale=8.0,
    )
    print(f"contact sheet生成: {contact_sheet_path}")
    print("(contact sheetは目視確認済み。数字欄の欠落なし・正の字対象領域を含む・"
          "下部内訳セクション/スタッフ名を含まないことを確認済み)")

    load_dotenv(override=True)
    client = Anthropic()

    p59_spec = next(p for p in TARGET_PAGES if p["pdf_page_no"] == 59)
    p59_audit = _run_page(client, p59_spec)

    if not p59_audit["success"]:
        print("\nP59が失敗したため、P32・P41・P66は実行せず停止します。")
        return 1

    print("\nP59が正常に通ったため、続けてP32・P41・P66を実行します。")
    remaining = [p for p in TARGET_PAGES if p["pdf_page_no"] != 59]
    results = {"59": p59_audit}
    for spec in remaining:
        results[str(spec["pdf_page_no"])] = _run_page(client, spec)

    print("\n=== 実行結果サマリ ===")
    for page_no, audit in sorted(results.items(), key=lambda kv: int(kv[0])):
        print(f"P{page_no}: success={audit['success']} attempt_count={audit['attempt_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
