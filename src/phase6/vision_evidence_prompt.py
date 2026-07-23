"""Phase 6: Vision抽出プロンプト文字列（Step 3A / vision evidence prompt）。

設計根拠: docs/PHASE_6_TRIPLE_EVIDENCE_SCHEMA_DESIGN_REVIEW.md 第4版
         および Step 3A実装指示（2026-07-22）

このモジュールはVision API呼び出しを行わない。将来Vision APIを呼び出す
モジュールが使用するプロンプト文字列を組み立てるだけに留める。

出力させるJSON契約の詳細は vision_evidence_contract.py
（EXAMPLE_VISION_EVIDENCE_PAYLOAD）を正とし、このプロンプトはその契約を
Vision側へ明示的に説明するためのテキストである。
EXAMPLE_VISION_EVIDENCE_PAYLOADの値はすべて架空のものであり、実際のいずれの
ページの実データでもない（実データ汚染防止のため）。
"""

from __future__ import annotations

import json

from src.phase6.vision_evidence_contract import EXAMPLE_VISION_EVIDENCE_PAYLOAD

__all__ = ["VISION_EVIDENCE_PROMPT_VERSION", "build_vision_evidence_prompt"]


# このプロンプト文字列自体のバージョン。プロンプトの内容を変更した場合に上げる。
VISION_EVIDENCE_PROMPT_VERSION = "1.0.0"


_CONTRACT_RULES = """\
【重要な契約条件】
- written_total.value と tally（正の字）を数えた結果のtally_countを混同しないこと。
  正の字を数えた結果をwritten_total.valueへ入れてはならない。
- 紹介・お声がけの数字欄が読めない場合はwritten_total.status="unreadable"、value=nullとすること。
- 正の字を確認していない（見ていない・判断していない）場合はtally.observation_status="not_observed"とすること。
- 正の字の線が見当たらない場合はtally.observation_status="no_marks_observed"とすること。
  no_marks_observedを0へ変換してはならない（complete_five_groups/remainder_strokesはnullのまま）。
- tally.observation_status="marks_present"の場合のみ、
  complete_five_groups・remainder_strokes・componentsを返すこと。
  marks_present以外ではこれらを一切出力しないこと（0も含めて出力しない）。
- tally_countは自分で計算して出力しないこと。Python側がcomplete_five_groups×5+remainder_strokes
  から計算する。
- confidenceはページ共通ではなく、店舗コード・紹介written_total・紹介tally・
  お声がけwritten_total・お声がけtallyそれぞれ独立に出力すること。
- CSV上の値をこのJSONへ一切含めないこと。CSVとの一致判定・review要否の判断もしないこと。
  それらは全てPython側の後続処理の責務である。
"""

_NEW_FORM_NOTES = """\
【新帳票での読み取り方針】
- 【案件】の合計行にある紹介・お声がけの数字欄を読むこと。
  下部の別セクション・内訳合計欄の数字を誤って合計行の値として使わないこと。
- 個別スタッフ行に正の字・画数が存在する場合は、行ごとにcomponentsへ記録すること
  （row_label・complete_five_groups・remainder_strokes）。
- 個別のスタッフ行が空欄であっても、自動的に0と解釈しないこと。
  空欄の場合はそのスタッフ行を無理にcomponentsへ含めない、あるいは該当スタッフ分の
  情報として扱わないこと（0を書いたことにしない）。
"""

_OLD_FORM_NOTES = """\
【旧帳票での読み取り方針】
- 数字欄（記載された合計数字）と正の字欄（tally）は位置・意味が別の欄であるため、
  混同せず分離して読むこと。
- この帳票版にその項目自体が存在しない場合はstatus="not_applicable"とすること。
- 欄は存在し見てはみたが判読できない場合はstatus="unreadable"とすること。
- 「旧スキーマ・旧処理では確認していない」という意味のstatus="not_observed"と
  "not_applicable"（項目自体が存在しない）・"unreadable"（見たが読めない）を混同しないこと。
"""

_STORE_CODE_NOTES = """\
【店舗コードの読み取り方針】
- 印刷済みの"AU1K"部分と、手書きの可変部分は分離して観測できるようにすること。
- raw_valueには画像上に実際に見えた文字列をそのまま入れること
  （このStepでは正規化・整形・訂正を行わない）。
- normalized_value（正規化後の値）はこのStepではVision側で作らないこと。
- 桁数チェック・近似候補探索・CSVマスターとの照合は、すべてPython後処理（後続のStep）の
  責務であり、Visionはそれらを一切行わないこと。
"""


def build_vision_evidence_prompt() -> str:
    """紹介/お声がけの数字欄・正の字・店舗コードを混ぜずに抽出させるためのプロンプト文字列を組み立てる。

    Vision APIの呼び出しはこの関数の責務外。呼び出し側が別途Vision APIへこの文字列を渡す。
    """
    example_json = json.dumps(EXAMPLE_VISION_EVIDENCE_PAYLOAD, ensure_ascii=False, indent=2)

    return f"""あなたは手書きFAX帳票の画像から、次の5項目を「混ぜずに」別々の証拠として読み取ります。

1. 店舗コード
2. 紹介総数の数字欄（written_total）
3. 紹介の正の字・画数（tally）
4. お声がけ総数の数字欄（written_total）
5. お声がけの正の字・画数（tally）

出力は必ず次のJSON契約に厳密に従うこと。契約外のキーを追加してはならない
（CSV値・CSV一致判定・review要否などは一切含めないこと）。

{_CONTRACT_RULES}
{_NEW_FORM_NOTES}
{_OLD_FORM_NOTES}
{_STORE_CODE_NOTES}
【出力JSON契約の例】
{example_json}
"""
