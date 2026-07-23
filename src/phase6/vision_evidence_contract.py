"""Phase 6: Vision抽出結果のJSON契約定義（Step 3A / vision evidence contract）。

設計根拠: docs/PHASE_6_TRIPLE_EVIDENCE_SCHEMA_DESIGN_REVIEW.md 第4版
         および Step 3A実装指示（2026-07-22, 2026-07-23修正）

このモジュールの責務は「Vision抽出結果として受け取るJSONの形を定義し、
契約違反（必須キー欠損・型不一致・未知enum値）を表す例外を提供する」ことに限定される。
実際のパース処理（JSON dict -> PageEvidence）は vision_evidence_parser.py の責務、
プロンプト文字列の組み立ては vision_evidence_prompt.py の責務。

このStepでは実装しないもの:
    - Vision APIの呼び出し
    - CSV resolver（Step 1）との結合
    - written_total / tally_count / csv値の三者比較
    - review routing・UI・Gmail連携
    - phase6_stage3_full.pyへの直接追記

JSON契約の要点（詳細はEXAMPLE_VISION_EVIDENCE_PAYLOADおよびparser側の検証を参照）:
    - written_total.value と tally.tally_count を混同しない。
      tally_countはVisionに直接出力させず、Python側（Step 2のTallyEvidence.tally_count
      property）で complete_five_groups×5+remainder_strokes から計算する。
      payloadにtally_countキーが含まれていても、パーサーは一切読み取らない。
    - confidenceはページ共通ではなく、店舗コード・紹介written_total・紹介tally・
      お声がけwritten_total・お声がけtallyそれぞれ独立に持つ。
    - CSV値・CSV一致判定・review判定はこのJSON契約に一切含めない。
    - normalized_value・format_status（店舗コードの桁数チェック等）はこのStepでは
      Visionに作らせない。Python後処理（将来のStep）の責務とする。
    - page_no・form_versionはpayload側の値を正本にしない。呼び出し側が別途持つ
      既知のページメタデータ（expected_page_no/expected_form_version）が正本であり、
      payload側の値は「その正本と一致しているかの照合対象」に限定する
      （vision_evidence_parser.parse_vision_evidence_response参照）。
    - not_observedは「旧JSON移行・旧処理では観測・抽出されていない」ことを表す状態であり、
      現行のVision処理の通常出力では使用しない。新しいVision抽出では、空欄と確認できた
      場合はno_value/no_marks_observed、確認したが読めない場合はunreadable、
      項目自体が帳票に存在しない場合はnot_applicableのいずれかを必ず選ぶ。
      旧JSONを取り込む場合に限り、パーサーのallow_not_observed=Trueを明示すること。

実データ汚染防止に関する注意:
    EXAMPLE_VISION_EVIDENCE_PAYLOADは契約の「形」を示すためのドキュメント用の例であり、
    値はすべて架空のもの（実際のP32等の値ではない）。実データ（例: P32の店舗コード
    4330093）はソースツリーに置かず、tests/phase6/fixtures/vision_evidence/ 配下の
    fixtureファイルにのみ保持する。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:
    from src.phase6.evidence_schema import PageEvidence

__all__ = [
    "VISION_EVIDENCE_CONTRACT_VERSION",
    "VisionEvidenceContractError",
    "VisionEvidenceAuditRecord",
    "EXAMPLE_VISION_EVIDENCE_PAYLOAD",
]


# このJSON契約自体のバージョン。契約の形（必須キー・enum値の意味）を変更した場合に上げる。
VISION_EVIDENCE_CONTRACT_VERSION = "1.0.0"


class VisionEvidenceContractError(Exception):
    """Vision JSONが契約（必須キー・型・既知のenum値・既知のページメタデータとの一致）を
    満たさない場合に送出する例外。

    Step 2のdataclassバリデーション（EvidenceValidationError）とは責務を分ける:
        - VisionEvidenceContractError: JSONの「形」の異常（構造・型・未知enum値・
          page_no/form_versionの不一致・許可されていないnot_observedの使用等）。
        - EvidenceValidationError: 値としては解釈できた上での意味的な不整合
          （marks_presentなのに画数がない、componentsの合計が合わない等）。
          こちらはStep 2のdataclass構築時にそのまま送出させ、ここで握り潰さない。
    """


@dataclass(frozen=True)
class VisionEvidenceAuditRecord:
    """PageEvidence（正本）と、変換元となった生のVision payload・契約/プロンプトの
    バージョンを一緒に保持する監査用の器。

    raw_payloadはあくまで監査・デバッグ用であり、PageEvidence（正本）には一切混ぜない。
    通常のパース経路（parse_vision_evidence_response）はPageEvidenceのみを返す。
    contract_version/prompt_versionは、後からどの契約・プロンプト版で抽出された
    結果かを追跡できるようにするための監査情報。
    """

    page_evidence: "PageEvidence"
    raw_payload: dict
    contract_version: str
    prompt_version: str


# 契約の「形」を示すためのドキュメント用の例。値はすべて架空のものであり、
# 実際のいずれのページの実データでもない（実データ汚染防止のため）。
# vision_evidence_prompt.py のプロンプト組み立て、およびテストの参考として使う。
EXAMPLE_VISION_EVIDENCE_PAYLOAD: Mapping[str, Any] = {
    "page_no": 1,
    "form_version": "new",
    "store_code": {
        "raw_value": "AU1K000001",
        "status": "observed",
        "confidence": "high",
        "notes": "",
    },
    "intro": {
        "written_total": {
            "value": 3,
            "status": "observed",
            "confidence": "high",
            "notes": "",
        },
        "tally": {
            "observation_status": "no_marks_observed",
            "complete_five_groups": None,
            "remainder_strokes": None,
            "confidence": "medium",
            "notes": "",
            "components": [],
        },
    },
    "voice": {
        "written_total": {
            "value": 5,
            "status": "observed",
            "confidence": "high",
            "notes": "",
        },
        "tally": {
            "observation_status": "no_marks_observed",
            "complete_five_groups": None,
            "remainder_strokes": None,
            "confidence": "medium",
            "notes": "",
            "components": [],
        },
    },
}
