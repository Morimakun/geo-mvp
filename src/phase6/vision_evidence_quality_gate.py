"""Phase 6: Step 3B v3 監査JSON品質ゲート（読み取り専用）。

設計根拠: Step 3B v3実装指示（2026-07-26）。

このモジュールの責務は「vision_evidence_client_v3.run_vision_evidence_pilot_page_v3()が
生成した監査JSON（dict）を読み取り専用で検査し、合否と項目別理由を返す」ことに限定される。

このモジュールが行わないこと:
    - 監査JSONの書き換え（ファイル保存はこのモジュールの責務外。呼び出し側スクリプトも
      書き込みを行わない）。
    - Vision APIの再実行・呼び出し。
    - CSV resolverとの結合・三者比較・review routing。

既存検証との重複回避（重要）:
    page_evidence部分の意味的整合性（cell_representationとwritten_total/tallyの
    整合等）は、監査JSON内のdictから src/phase6/evidence_schema.py の
    NumericFieldEvidence等のdataclassを再構築し、その__post_init__
    （EvidenceValidationError）にそのまま委譲する。numeric/tally/blank/unreadable/
    mixedの5パターンの判定ルールは、このモジュールでは一切再実装しない
    （evidence_schema.pyが唯一の実装）。contract_version/prompt_versionの
    期待値も、vision_evidence_contract.py/vision_evidence_prompt.pyの定数を
    そのまま参照し、このモジュールへ別途ハードコードしない。

一般品質ゲート（check_general_quality_gate）とP59限定の採点条件
（check_p59_profile）は責務を分離する。P59限定プロフィールは、Step 3A/3Bで
人手確認済みの一部フィールド（紹介written_total=0・紹介tally=no_marks_observed等）
のみを対象とし、未確認のフィールド（お声がけ値・店舗コード・他の正の字・CSV値）は
一切参照・採点しない。
"""

from __future__ import annotations

import re
from typing import Any, Optional

from src.phase6.evidence_schema import (
    CellRepresentation,
    Confidence,
    EvidenceStatus,
    EvidenceValidationError,
    NumericFieldEvidence,
    TallyComponent,
    TallyEvidence,
    TallyObservationStatus,
    WrittenTotalEvidence,
)
from src.phase6.vision_evidence_contract import VISION_EVIDENCE_CONTRACT_VERSION
from src.phase6.vision_evidence_prompt import VISION_EVIDENCE_PROMPT_VERSION

__all__ = [
    "QualityGateError",
    "check_general_quality_gate",
    "check_p59_profile",
]

# P59は2026-06-25の営業日で確認された、Step 3A/3B時点の人手確認済み事項のみを対象とする
# （お声がけ値・店舗コード・他の正の字状態・CSV値は未確認のため一切採点しない）。
_P59_PAGE_NO = 59
_P59_EXPECTED_FORM_VERSION = "new"
_P59_SELECTED_BUSINESS_DATE = "2026-06-25"

_SECRET_KEY_SUBSTRINGS = (
    "api_key",
    "apikey",
    "authorization",
    "secret",
    "anthropic_api_key",
    "bearer",
)
_FORBIDDEN_IMAGE_KEY_SUBSTRINGS = ("image_bytes", "image_base64", "image_data", "base64")
# base64画像本体らしき、非常に長い英数字+記号だけの文字列（sha256の16進64文字とは
# 明確に区別できる長さ・文字種のしきい値）。
_BASE64_LIKE_RE = re.compile(r"^[A-Za-z0-9+/]{200,}={0,2}$")


class QualityGateError(Exception):
    """監査JSONの構造が壊れていて、そのフィールドの検査を続行できない場合に送出する
    （このモジュール内部でのみ使用し、呼び出し側へは伝播させず判定結果へ変換する）。"""


# ============================================================
# 監査JSON全体の走査（秘密情報・画像データ混入チェック用）
# ============================================================
def _walk(obj: Any, path: str = ""):
    if isinstance(obj, dict):
        for key, value in obj.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield child_path, key, value
            yield from _walk(value, child_path)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            child_path = f"{path}[{index}]"
            yield from _walk(value, child_path)


def _find_secret_like_keys(audit: dict) -> list:
    return [
        path
        for path, key, _value in _walk(audit)
        if any(s in str(key).lower() for s in _SECRET_KEY_SUBSTRINGS)
    ]


def _find_forbidden_image_data(audit: dict) -> list:
    found = []
    for path, key, value in _walk(audit):
        if any(s in str(key).lower() for s in _FORBIDDEN_IMAGE_KEY_SUBSTRINGS):
            found.append(path)
        elif isinstance(value, str) and _BASE64_LIKE_RE.match(value):
            found.append(path)
    return found


# ============================================================
# page_evidenceのdictからdataclassを再構築する（既存の__post_init__検証に委譲する）
# ============================================================
def _rehydrate_numeric_field(d: Optional[dict]) -> NumericFieldEvidence:
    if not isinstance(d, dict):
        raise QualityGateError("numeric field evidenceがオブジェクト(dict)ではありません")
    written = d.get("written_total")
    tally = d.get("tally")
    if not isinstance(written, dict) or not isinstance(tally, dict):
        raise QualityGateError("written_total/tallyがオブジェクト(dict)ではありません")

    try:
        written_total = WrittenTotalEvidence(
            value=written.get("value"),
            status=EvidenceStatus(written["status"]),
            confidence=Confidence(written["confidence"]) if written.get("confidence") else None,
            notes=written.get("notes"),
        )
        components = [
            TallyComponent(
                row_label=c.get("row_label"),
                complete_five_groups=c["complete_five_groups"],
                remainder_strokes=c["remainder_strokes"],
            )
            for c in (tally.get("components") or [])
        ]
        tally_evidence = TallyEvidence(
            observation_status=TallyObservationStatus(tally["observation_status"]),
            complete_five_groups=tally.get("complete_five_groups"),
            remainder_strokes=tally.get("remainder_strokes"),
            confidence=Confidence(tally["confidence"]) if tally.get("confidence") else None,
            notes=tally.get("notes"),
            components=components,
        )
        raw_cell_representation = d.get("cell_representation")
        cell_representation = (
            CellRepresentation(raw_cell_representation) if raw_cell_representation else None
        )
    except (KeyError, ValueError) as exc:
        raise QualityGateError(f"監査JSON内のevidence構造が不正です: {exc}") from exc

    # 意味的整合性（numeric/tally/blank/unreadable/mixedの5パターン判定）はここで
    # 再実装せず、NumericFieldEvidence.__post_init__（Step 2）へそのまま委譲する。
    return NumericFieldEvidence(
        written_total=written_total, tally=tally_evidence, cell_representation=cell_representation
    )


# ============================================================
# 一般品質ゲート
# ============================================================
def check_general_quality_gate(audit: dict) -> list:
    """監査JSON（vision_evidence_client_v3.run_vision_evidence_pilot_page_v3()の出力）を
    一般品質ゲートで検査する。監査JSONは書き換えない。Vision APIは呼び出さない。

    Returns:
        [(check_name, passed, detail), ...]。常にリストを返す（例外を投げない）。
    """
    results: list = []

    def add(name: str, passed: bool, detail: str = "") -> bool:
        results.append((name, passed, detail))
        return passed

    if not isinstance(audit, dict):
        add("audit_is_dict", False, "監査JSONがオブジェクト(dict)ではありません")
        return results

    registration = audit.get("registration")
    reg_status = registration.get("status") if isinstance(registration, dict) else None
    add("registration_matched", reg_status == "matched", f"registration.status={reg_status!r}")

    add("success_true", audit.get("success") is True, f"success={audit.get('success')!r}")
    add(
        "attempt_count_is_1",
        audit.get("attempt_count") == 1,
        f"attempt_count={audit.get('attempt_count')!r}",
    )

    attempts = audit.get("attempts")
    attempts_ok = isinstance(attempts, list) and len(attempts) == 1
    add(
        "attempts_has_exactly_one_entry",
        attempts_ok,
        "" if attempts_ok else f"attempts={attempts!r}",
    )
    if attempts_ok:
        attempt_0_success = attempts[0].get("success") if isinstance(attempts[0], dict) else None
        add("attempt_0_success_true", attempt_0_success is True, f"attempts[0].success={attempt_0_success!r}")
    else:
        add("attempt_0_success_true", False, "attemptsが1件ではないため確認できません")

    add(
        "contract_version_matches",
        audit.get("contract_version") == VISION_EVIDENCE_CONTRACT_VERSION,
        f"contract_version={audit.get('contract_version')!r}（期待値: {VISION_EVIDENCE_CONTRACT_VERSION!r}）",
    )
    add(
        "prompt_version_matches",
        audit.get("prompt_version") == VISION_EVIDENCE_PROMPT_VERSION,
        f"prompt_version={audit.get('prompt_version')!r}（期待値: {VISION_EVIDENCE_PROMPT_VERSION!r}）",
    )

    page_evidence = audit.get("page_evidence")
    page_evidence_present = isinstance(page_evidence, dict)
    add(
        "page_evidence_present",
        page_evidence_present,
        "" if page_evidence_present else "page_evidenceが存在しません",
    )

    for label, field_name in (("intro", "intro_evidence"), ("voice", "voice_evidence")):
        if not page_evidence_present:
            add(f"{label}_evidence_present", False, "page_evidenceが存在しないため確認できません")
            continue

        field_dict = page_evidence.get(field_name)
        if not isinstance(field_dict, dict):
            add(f"{label}_evidence_present", False, f"{field_name}が存在しません")
            continue
        add(f"{label}_evidence_present", True)

        raw_cell_representation = field_dict.get("cell_representation")
        add(
            f"{label}_cell_representation_present",
            raw_cell_representation is not None,
            "" if raw_cell_representation is not None else "cell_representationがNoneです",
        )

        try:
            rehydrated = _rehydrate_numeric_field(field_dict)
        except (QualityGateError, EvidenceValidationError) as exc:
            add(f"{label}_cell_representation_consistent", False, str(exc))
            continue
        add(f"{label}_cell_representation_consistent", True)

        if rehydrated.cell_representation == CellRepresentation.NUMERIC:
            add(
                f"{label}_numeric_written_total_observed",
                rehydrated.written_total.status == EvidenceStatus.OBSERVED,
            )
            add(
                f"{label}_numeric_written_total_value_present",
                rehydrated.written_total.value is not None,  # 0も正常値として許可する
            )
            add(
                f"{label}_numeric_tally_no_marks_observed",
                rehydrated.tally.observation_status == TallyObservationStatus.NO_MARKS_OBSERVED,
            )
            add(f"{label}_numeric_tally_count_none", rehydrated.tally.tally_count is None)
            add(f"{label}_numeric_components_empty", rehydrated.tally.components == [])

    secret_keys = _find_secret_like_keys(audit)
    add(
        "no_secret_like_fields",
        not secret_keys,
        f"秘密情報らしきキーを検出: {secret_keys}" if secret_keys else "",
    )

    forbidden_image_data = _find_forbidden_image_data(audit)
    add(
        "no_image_data_only_sha256",
        not forbidden_image_data,
        f"画像データらしきキー・値を検出: {forbidden_image_data}" if forbidden_image_data else "",
    )

    return results


# ============================================================
# P59限定プロフィール（一般品質ゲートとは独立）
# ============================================================
def check_p59_profile(audit: dict) -> list:
    """P59限定の採点条件のみを検査する。一般品質ゲート（check_general_quality_gate）
    とは独立した関数であり、呼び出し側が必要な場合にのみ両方の結果を組み合わせる。

    採点しないもの（一切参照しない）: お声がけ値、店舗コード、未確認の正の字、CSV値。

    Returns:
        [(check_name, passed, detail), ...]。常にリストを返す（例外を投げない）。
    """
    results: list = []

    def add(name: str, passed: bool, detail: str = "") -> bool:
        results.append((name, passed, detail))
        return passed

    if not isinstance(audit, dict):
        add("audit_is_dict", False, "監査JSONがオブジェクト(dict)ではありません")
        return results

    add("page_no_is_59", audit.get("page_no") == _P59_PAGE_NO, f"page_no={audit.get('page_no')!r}")
    add(
        "expected_form_version_is_new",
        audit.get("expected_form_version") == _P59_EXPECTED_FORM_VERSION,
        f"expected_form_version={audit.get('expected_form_version')!r}",
    )
    add(
        "selected_business_date_matches",
        audit.get("selected_business_date") == _P59_SELECTED_BUSINESS_DATE,
        f"selected_business_date={audit.get('selected_business_date')!r}",
    )

    page_evidence = audit.get("page_evidence")
    if not isinstance(page_evidence, dict):
        add("intro_profile_checkable", False, "page_evidenceが存在しないため採点できません")
        return results

    intro = page_evidence.get("intro_evidence")
    if not isinstance(intro, dict):
        add("intro_profile_checkable", False, "intro_evidenceが存在しないため採点できません")
        return results
    add("intro_profile_checkable", True)

    add(
        "intro_cell_representation_is_numeric",
        intro.get("cell_representation") == "numeric",
        f"intro.cell_representation={intro.get('cell_representation')!r}",
    )

    written_total = intro.get("written_total") if isinstance(intro.get("written_total"), dict) else {}
    add(
        "intro_written_total_value_is_0",
        written_total.get("value") == 0,
        f"intro.written_total.value={written_total.get('value')!r}",
    )

    tally = intro.get("tally") if isinstance(intro.get("tally"), dict) else {}
    add(
        "intro_tally_observation_status_is_no_marks_observed",
        tally.get("observation_status") == "no_marks_observed",
        f"intro.tally.observation_status={tally.get('observation_status')!r}",
    )
    add(
        "intro_tally_count_is_none",
        tally.get("tally_count") is None,
        f"intro.tally.tally_count={tally.get('tally_count')!r}",
    )
    add(
        "intro_tally_components_empty",
        tally.get("components") == [],
        f"intro.tally.components={tally.get('components')!r}",
    )

    return results
