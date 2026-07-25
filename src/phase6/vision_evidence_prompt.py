"""Phase 6: Vision抽出プロンプト文字列（Step 3A / vision evidence prompt）。

設計根拠: docs/PHASE_6_TRIPLE_EVIDENCE_SCHEMA_DESIGN_REVIEW.md 第4版
         および Step 3A実装指示（2026-07-22）、Step 3B実装指示（2026-07-23）

このモジュールはVision API呼び出しを行わない。将来Vision APIを呼び出す
モジュールが使用するプロンプト文字列を組み立てるだけに留める。

出力させるJSON契約の詳細は vision_evidence_contract.py
（EXAMPLE_VISION_EVIDENCE_PAYLOAD）を正とし、このプロンプトはその契約を
Vision側へ明示的に説明するためのテキストである。
EXAMPLE_VISION_EVIDENCE_PAYLOADの値はすべて架空のものであり、実際のいずれの
ページの実データでもない（実データ汚染防止のため）。

Step 3B（実画像パイロット）での変更点（v1.1.0）:
    - 帳票版（新/旧）の判定基準を明示（Step 3Aでは読み取り方針のみで判定基準が
      欠けていたため追加）。
    - スタッフ名等、契約外の個人情報を抽出しないことを明示。
    - build_vision_evidence_prompt(page_no=...) で、既知のページ番号を
      プロンプト末尾に追記できるようにした（page_noは帳票に印字されておらず
      画像から独立に観測できないため、PDFページ位置として明示的に伝える。
      呼び出し側はこれをVisionの出力page_noとの照合にのみ使い、正本にはしない）。

Step 3B v1パイロット後の修正（v2.0.0）:
    - v1ではフルページ画像+新帳票合計行の広めの固定クロップ(y=215-290pt)を渡していたが、
      そのクロップが【内訳】セクション（個別項目の行）まで含んでしまい、そこにある
      紹介・お声がけとは無関係な手書き記号を正の字として誤認する事故が実際に発生した
      （P59: 「eo光ユーザー数」「未購入件数(MT)」の記号をtallyのcomponentsとして誤検出）。
    - これを受け、build_region_scoped_prompt() を新設。フルページ画像を主入力とせず、
      帳票版ごとに固定した狭い対象領域（region_id）の画像のみを渡し、各証拠は
      指定されたregion_idの画像だけを根拠にすること、対象領域外の情報で値を補わない
      ことを明示的に指示する。
    - build_vision_evidence_prompt()（v1のフルページ向けプロンプト）はテスト・後方
      互換のためそのまま残すが、実画像パイロットではbuild_region_scoped_prompt()を使う。
"""

from __future__ import annotations

import json
from typing import Optional

from src.phase6.vision_evidence_contract import EXAMPLE_VISION_EVIDENCE_PAYLOAD

__all__ = [
    "VISION_EVIDENCE_PROMPT_VERSION",
    "build_vision_evidence_prompt",
    "build_region_scoped_prompt",
    "build_cell_scoped_prompt_v3",
]


# このプロンプト文字列自体のバージョン。プロンプトの内容を変更した場合に上げる。
#
# 3.0.0（Step 3B v3, 2026-07-25）: 同一セルをwritten用・tally用の別領域として
#   二重送信する構造をやめ、1セル(cell_id)につきcontext/detailの2画像だけを送る
#   構造へ変更（build_cell_scoped_prompt_v3）。cell_representation
#   （numeric/tally/blank/unreadable/mixed）の自己申告を新たに指示する。
VISION_EVIDENCE_PROMPT_VERSION = "3.0.0"


_FORM_VERSION_CLASSIFICATION = """\
【帳票版（新/旧）の判定基準】
- 新帳票（2026/6/21版）: 通し番号（daily_report_no/tablet_no相当の欄）・提出区分
  （初回/再送）の欄がある。
- 旧帳票（2026/4/1版）: 上記の欄がなく、店舗名が行頭に印字されている。
- どちらか判定できない場合はform_version="new"/"old"のいずれかに無理に決めず、
  read取れた根拠をnotesへ記録すること。
"""

_PII_SCOPE_NOTES = """\
【対象外の個人情報】
- スタッフ名・スタッフID等、この契約のJSONに定義されていない項目は一切抽出・出力しないこと。
  出力してよいのは契約で定義された5項目（店舗コード・紹介written_total・紹介tally・
  お声がけwritten_total・お声がけtally）に関する情報のみ。
"""

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


def build_vision_evidence_prompt(*, page_no: Optional[int] = None) -> str:
    """紹介/お声がけの数字欄・正の字・店舗コードを混ぜずに抽出させるためのプロンプト文字列を組み立てる。

    Vision APIの呼び出しはこの関数の責務外。呼び出し側が別途Vision APIへこの文字列を渡す。

    Args:
        page_no: 既知のPDFページ番号（1始まり）。指定した場合、プロンプト末尾に
            「この画像のpage_noは{page_no}です」という一文を追記する。page_noは
            帳票に印字されていない（画像から独立に観測できない）ため、呼び出し側の
            既知の値をそのまま伝える。JSON出力のpage_noはパーサー側で
            expected_page_noと照合されるのみで、正本としては扱われない。
    """
    example_json = json.dumps(EXAMPLE_VISION_EVIDENCE_PAYLOAD, ensure_ascii=False, indent=2)

    prompt = f"""あなたは手書きFAX帳票の画像から、次の5項目を「混ぜずに」別々の証拠として読み取ります。

1. 店舗コード
2. 紹介総数の数字欄（written_total）
3. 紹介の正の字・画数（tally）
4. お声がけ総数の数字欄（written_total）
5. お声がけの正の字・画数（tally）

出力は必ず次のJSON契約に厳密に従うこと。契約外のキーを追加してはならない
（CSV値・CSV一致判定・review要否などは一切含めないこと）。

{_CONTRACT_RULES}
{_FORM_VERSION_CLASSIFICATION}
{_NEW_FORM_NOTES}
{_OLD_FORM_NOTES}
{_STORE_CODE_NOTES}
{_PII_SCOPE_NOTES}
【出力JSON契約の例】
{example_json}
"""
    if page_no is not None:
        prompt += (
            f"\nこの画像のpage_noは{page_no}です。JSON出力のpage_noにこの値を"
            "そのまま反映してください（page_no自体は帳票に印字された情報ではありません）。\n"
        )
    return prompt


# ============================================================
# Step 3B v2: 領域限定（region-scoped）プロンプト
# ============================================================
_REGION_ISOLATION_RULES = """\
【領域限定の絶対ルール（最重要）】
- 各証拠（店舗コード・紹介written_total・紹介tally・お声がけwritten_total・
  お声がけtally）は、その証拠に対応するregion_idの画像だけを根拠にすること。
- 送っていない別の画像・別セクション・下部の内訳合計欄から値を補ってはならない。
  ある画像に見えなかった情報を、記憶や推測、他の画像から埋め合わせないこと。
- tallyのcomponentsに、帳票上に印字された項目名（スタッフ名・サービス名等）を
  そのまま転記しないこと。行を区別する必要がある場合は"row_1"のような匿名の
  識別子を使うこと。
- 対象領域の外にある線・記号・マーク（罫線、他セクションの手書き記号等）を
  正の字としてカウントしないこと。
- 対象領域内に画線が一切見当たらない場合はobservation_status="no_marks_observed"
  とすること。
- 対象領域内の記載が薄い・かすれている等で判別できない場合は
  observation_status="unreadable"とすること。
- 確信が持てないのに推測でobservation_status="marks_present"にしないこと。
  marks_presentは、対象領域内に正の字の画線が実際に見えた場合のみ選ぶこと。
"""

_OUTPUT_LENGTH_RULES = """\
【出力形式・長さの制約】
- 必ずsubmit_vision_evidenceツールの引数として結果を返すこと。
  ツール呼び出し以外の自由文（前置き・説明・要約）は一切出力しないこと。
- マークダウンのコードフェンス（```等）を使わないこと。
- 各notesフィールドは1文・日本語で80文字程度までの短い説明に限定すること。
  画像の詳細な描写や長い推論過程をnotesへ書かないこと。
"""

_STORE_CODE_INTEGRITY_NOTE = """\
【店舗コードについての注意】
- この画像には正解の店舗コード・CSV上の値・過去の抽出結果は一切含まれていません。
  画像に実際に見えた文字だけをraw_valueへ転記すること。
- 見えた通りに自信を持って読めない場合は、confidenceを正直にlow/mediumとすること。
  無理に高いconfidenceを付けないこと。
"""


def build_region_scoped_prompt(
    *,
    page_no: int,
    form_version: str,
    region_ids_in_order: list,
) -> str:
    """帳票版ごとに固定した対象領域（region_id）の画像だけを渡す場合のプロンプトを組み立てる。

    フルページ画像は渡さない前提。各画像は本関数が生成する順序どおりに
    region_ids_in_orderで渡されることを想定し、その対応関係を明示する。

    Args:
        page_no: 既知のPDFページ番号（1始まり）。page_noは帳票に印字されていないため
            明示的に伝える（Vision出力のpage_noは照合対象に限定され、正本にはしない）。
        form_version: 既知の帳票版（"new"|"old"）。region_idの構成から呼び出し側が
            既に把握している値であり、Visionに推定させる必要はないため明示的に伝える
            （Vision出力のform_versionも照合対象に限定され、正本にはしない）。
        region_ids_in_order: 渡す画像の順序に対応するregion_idのリスト。
    """
    region_list_text = "\n".join(
        f"{i + 1}枚目: region_id=\"{rid}\"" for i, rid in enumerate(region_ids_in_order)
    )
    allowed_ids_text = "、".join(f'"{rid}"' for rid in region_ids_in_order)

    return f"""あなたは手書きFAX帳票の、あらかじめ切り出された狭い対象領域の画像から、
店舗コード・紹介/お声がけの数字欄・紹介/お声がけの正の字を「混ぜずに」読み取ります。
フルページ画像は渡されていません。渡された各画像はそれぞれ1つの証拠に対応する
固定領域のクロップです。

【渡された画像とregion_idの対応】
{region_list_text}

各証拠のregion_idには、必ず上記のいずれか（{allowed_ids_text}）を
そのまま設定すること。それ以外の値や、送っていない領域名を出力してはならない。

出力は必ずsubmit_vision_evidenceツールの契約に厳密に従うこと。

{_REGION_ISOLATION_RULES}
{_CONTRACT_RULES}
{_PII_SCOPE_NOTES}
{_STORE_CODE_INTEGRITY_NOTE}
{_OUTPUT_LENGTH_RULES}
この画像のpage_noは{page_no}、form_versionは"{form_version}"です。
ツール引数のpage_no/form_versionにこれらの値をそのまま反映してください
（いずれも画像から独立に観測できる情報ではないため、既知の値を伝えています）。
"""


# ============================================================
# Step 3B v3: セル単位（cell-scoped）プロンプト
# 同じセルをwritten用・tally用の別々の証拠として二重送信しない（1セル=1組の
# context/detail画像）。cell_representationの自己申告を新たに指示する。
# ============================================================
_CELL_REPRESENTATION_RULES = """\
【cell_representationの分類（必須）】
- 紹介・お声がけそれぞれのセルについて、次の5分類のいずれか1つを選び、
  cell_representationとして必ず出力すること。
  - "numeric": 算用数字が書かれている（0も含む）。正の字は書かれていない。
  - "tally": 正の字だけが書かれている。算用数字は書かれていない。
  - "blank": 算用数字も正の字も書かれていない（真の空欄）。
  - "unreadable": 何か書かれているが判読できない
    （この場合、written_total.status・tally.observation_statusの両方を
    "unreadable"とすること。片方だけをunreadableにしないこと）。
  - "mixed": 算用数字と正の字の両方が実際に書かれている異常系
    （この場合のみwritten_total.status="observed"かつ
    tally.observation_status="marks_present"を両立させてよい）。
- 上記5分類のどれにも一致しない組み合わせ（例: 算用数字は読めるが正の字だけ
  判読不能、といった片側だけのunreadable）を出力してはならない。
  実際に見えた内容がこの5分類のどれにも当てはまらないと感じた場合は、
  最も安全側（unreadableまたはmixed）に倒し、notesへ具体的な状況を記録すること。
"""

_CELL_ISOLATION_RULES = """\
【セル単位の絶対ルール（最重要）】
- 各セル（紹介・お声がけ・店舗コード）について、そのセルに対応する
  cell_id__context / cell_id__detail の2枚の画像だけを根拠にすること。
  同じセルについて、算用数字用の画像と正の字用の画像が別々に渡されることは
  ない（1セル=1組の画像）。
- 各証拠のcell_idには、必ず渡された画像のcell_id（末尾の__context/__detailを
  除いた部分）と同じ値を設定すること。送っていないセルのcell_idを参照しては
  ならない。
- 送っていない別のセルの画像・記憶・推測から値を補ってはならない。
"""


def build_cell_scoped_prompt_v3(
    *,
    page_no: int,
    form_version: str,
    cell_ids_in_order: list,
) -> str:
    """Step 3B v3: 1セル(cell_id)につきcontext/detailの2画像だけを渡す場合の
    プロンプトを組み立てる。フルページ画像・v2の5領域構造（written/tally別々の
    region_id）は使わない。

    Args:
        page_no: 既知のPDFページ番号（1始まり）。
        form_version: 既知の帳票版（"new"|"old"）。
        cell_ids_in_order: 渡す画像の元になったcell_idのリスト（例:
            ["intro", "voice"]、店舗コードがあれば"store_code"を含む）。
            実際に渡す画像は各cell_idにつき{cell_id}__context/{cell_id}__detailの
            2枚ずつになる。
    """
    cell_list_text = "、".join(f'"{cid}"' for cid in cell_ids_in_order)

    return f"""あなたは手書きFAX帳票の、あらかじめ切り出されたセル単位の画像から、
店舗コード・紹介/お声がけの数字欄・正の字を読み取ります。
フルページ画像は渡されていません。渡された画像はセル(cell_id)ごとに
context（周辺文脈を含む広めの切り出し）・detail（数字/正の字を判読するための
密な切り出し）の2枚1組です。

【今回送信するcell_id】
{cell_list_text}

出力は必ずsubmit_vision_evidenceツールの契約に厳密に従うこと。

{_CELL_ISOLATION_RULES}
{_CELL_REPRESENTATION_RULES}
{_CONTRACT_RULES}
{_PII_SCOPE_NOTES}
{_STORE_CODE_INTEGRITY_NOTE}
{_OUTPUT_LENGTH_RULES}
この画像のpage_noは{page_no}、form_versionは"{form_version}"です。
ツール引数のpage_no/form_versionにこれらの値をそのまま反映してください
（いずれも画像から独立に観測できる情報ではないため、既知の値を伝えています）。
"""
