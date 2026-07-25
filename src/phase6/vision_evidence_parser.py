"""Phase 6: Vision抽出JSON -> PageEvidence パーサー（Step 3A / vision evidence parser）。

設計根拠: docs/PHASE_6_TRIPLE_EVIDENCE_SCHEMA_DESIGN_REVIEW.md 第4版
         および Step 3A実装指示（2026-07-22, 2026-07-23修正）

このモジュールの責務は「Vision抽出結果のJSON(dict)を、Step 2で定義した
PageEvidenceへ安全に変換する」ことに限定される。Vision API呼び出し・
CSV resolverとの結合・三者比較・review routing・UIには一切関与しない。

責務の分離（重要）:
    - このモジュール自身が検証するのは「JSONの形」（必須キーの有無・型・
      既知のenum値かどうか・既知のページメタデータとの一致）のみ。
      異常時は VisionEvidenceContractError を送出する。
    - 値としては解釈できた上での意味的な整合性
      （marks_presentなのに画数がない、no_marks_observedなのに画数がある、
      componentsの合計と集約値が一致しない、observedなのにvalueがない等）は
      一切ここで判定せず、Step 2のdataclass（WrittenTotalEvidence/TallyEvidence/...）
      の __post_init__ にそのまま委譲する。そちらは EvidenceValidationError を送出する。
    - JSONの値は一切信用しない。bool・小数・負数は数値として受け付けない
      （2.0のような整数値に見える小数であっても、CSV resolverと異なり一切整数化しない）。
    - tally_count・component側のcount相当のキーがpayloadに含まれていても、
      このパーサーは一切読み取らない。tally_countは常にStep 2の
      TallyEvidence.tally_count property（complete_five_groups×5+remainder_strokes）
      から計算される値のみを正本とする。
    - selected_business_dateは常に引数を正本とする。payload内に日付らしき
      キーが含まれていても読み取らない（無視する）。
    - page_no・form_versionも同様に、呼び出し側が既に把握している既知の
      ページメタデータ（expected_page_no/expected_form_version）を正本とする。
      payload側の値はその正本と一致しているかの照合対象に限定し、不一致なら
      VisionEvidenceContractErrorとする（store_code_resolution_source等から
      帳票版を推定することはしない）。
    - not_observedは「旧JSON移行・旧処理では観測・抽出されていない」ことを表す
      状態であり、現行のVision処理の通常出力では使用しない。デフォルト
      （allow_not_observed=False）では、payload中のいずれかのstatus/
      observation_statusがnot_observedだった場合にVisionEvidenceContractErrorと
      する。旧JSON互換データを明示的に扱う場合のみallow_not_observed=Trueを渡すこと。
"""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Optional

from src.phase6.evidence_schema import (
    CellRepresentation,
    Confidence,
    EvidenceStatus,
    NumericFieldEvidence,
    PageEvidence,
    StoreCodeEvidence,
    StoreCodeFormatStatus,
    TallyComponent,
    TallyEvidence,
    TallyObservationStatus,
    WrittenTotalEvidence,
)
from src.phase6.vision_evidence_contract import (
    VISION_EVIDENCE_CONTRACT_VERSION,
    VisionEvidenceAuditRecord,
    VisionEvidenceContractError,
)
from src.phase6.vision_evidence_prompt import VISION_EVIDENCE_PROMPT_VERSION

__all__ = [
    "parse_vision_evidence_response",
    "parse_vision_evidence_response_with_audit",
]


# ============================================================
# ヘルパー: 構造検証
# ============================================================
def _require(d: Mapping[str, Any], key: str, path: str) -> Any:
    if key not in d:
        raise VisionEvidenceContractError(f"{path}: 必須キー'{key}'が存在しません")
    return d[key]


def _require_mapping(d: Mapping[str, Any], key: str, path: str) -> Mapping[str, Any]:
    value = _require(d, key, path)
    if not isinstance(value, Mapping):
        raise VisionEvidenceContractError(f"{path}: オブジェクト(dict)である必要があります")
    return value


def _map_enum(enum_cls, raw: Any, *, path: str):
    if not isinstance(raw, str):
        raise VisionEvidenceContractError(f"{path}: 文字列である必要があります: {raw!r}")
    try:
        return enum_cls(raw)
    except ValueError:
        valid = ", ".join(m.value for m in enum_cls)
        raise VisionEvidenceContractError(
            f"{path}: 未知の値です: {raw!r}（有効な値: {valid}）"
        ) from None


def _reject_not_observed(status, *, path: str, allow_not_observed: bool) -> None:
    is_not_observed = status in (EvidenceStatus.NOT_OBSERVED, TallyObservationStatus.NOT_OBSERVED)
    if is_not_observed and not allow_not_observed:
        raise VisionEvidenceContractError(
            f"{path}: not_observedは現行のVision契約の通常出力では使用できません"
            "（旧JSON移行・旧処理の未観測を表す状態のため）。"
            "空欄と確認できた場合はno_value/no_marks_observed、確認したが読めない場合は"
            "unreadable、項目自体が帳票に存在しない場合はnot_applicableを使用してください。"
            "旧JSON互換データを扱う場合のみ、明示的にallow_not_observed=Trueを指定してください。"
        )


def _map_evidence_status(raw: Any, *, path: str, allow_not_observed: bool) -> EvidenceStatus:
    status = _map_enum(EvidenceStatus, raw, path=path)
    _reject_not_observed(status, path=path, allow_not_observed=allow_not_observed)
    return status


def _map_tally_status(
    raw: Any, *, path: str, allow_not_observed: bool
) -> TallyObservationStatus:
    status = _map_enum(TallyObservationStatus, raw, path=path)
    _reject_not_observed(status, path=path, allow_not_observed=allow_not_observed)
    return status


def _map_confidence(raw: Any, *, path: str) -> Optional[Confidence]:
    if raw is None:
        return None
    return _map_enum(Confidence, raw, path=path)


def _parse_strict_nonneg_int(raw: Any, *, path: str) -> int:
    """boolは数値として受け付けない。小数は（is_integer()であっても）一切整数化しない。
    負数も受け付けない。"""
    if isinstance(raw, bool):
        raise VisionEvidenceContractError(f"{path}: bool値は数値として受け付けません: {raw!r}")
    if isinstance(raw, float):
        raise VisionEvidenceContractError(f"{path}: 小数は受け付けません（整数のみ）: {raw!r}")
    if not isinstance(raw, int):
        raise VisionEvidenceContractError(f"{path}: 整数である必要があります: {raw!r}")
    if raw < 0:
        raise VisionEvidenceContractError(f"{path}: 負数は受け付けません: {raw!r}")
    return raw


def _parse_optional_strict_nonneg_int(raw: Any, *, path: str) -> Optional[int]:
    if raw is None:
        return None
    return _parse_strict_nonneg_int(raw, path=path)


def _optional_str(raw: Any, *, path: str) -> Optional[str]:
    if raw is not None and not isinstance(raw, str):
        raise VisionEvidenceContractError(f"{path}: 文字列またはnullである必要があります: {raw!r}")
    return raw


# ============================================================
# ヘルパー: 各サブ構造のパース
# ============================================================
def _parse_written_total(
    d: Mapping[str, Any], *, path: str, allow_not_observed: bool
) -> WrittenTotalEvidence:
    status = _map_evidence_status(
        _require(d, "status", f"{path}.status"),
        path=f"{path}.status",
        allow_not_observed=allow_not_observed,
    )
    value = _parse_optional_strict_nonneg_int(
        _require(d, "value", f"{path}.value"), path=f"{path}.value"
    )
    confidence = _map_confidence(d.get("confidence"), path=f"{path}.confidence")
    notes = _optional_str(d.get("notes"), path=f"{path}.notes")

    # 意味的な整合性（observedならvalue必須、それ以外ならvalue禁止）はStep 2へ委譲する。
    return WrittenTotalEvidence(value=value, status=status, confidence=confidence, notes=notes)


def _parse_tally_component(raw: Any, *, path: str) -> TallyComponent:
    if not isinstance(raw, Mapping):
        raise VisionEvidenceContractError(f"{path}: オブジェクト(dict)である必要があります")
    row_label = _optional_str(raw.get("row_label"), path=f"{path}.row_label")
    five = _parse_strict_nonneg_int(
        _require(raw, "complete_five_groups", f"{path}.complete_five_groups"),
        path=f"{path}.complete_five_groups",
    )
    remainder = _parse_strict_nonneg_int(
        _require(raw, "remainder_strokes", f"{path}.remainder_strokes"),
        path=f"{path}.remainder_strokes",
    )
    # componentにcount/tally_count相当のキーが含まれていても読み取らない。
    # count はStep 2の TallyComponent.count property が再計算する。
    return TallyComponent(row_label=row_label, complete_five_groups=five, remainder_strokes=remainder)


def _parse_tally(
    d: Mapping[str, Any], *, path: str, allow_not_observed: bool
) -> TallyEvidence:
    observation_status = _map_tally_status(
        _require(d, "observation_status", f"{path}.observation_status"),
        path=f"{path}.observation_status",
        allow_not_observed=allow_not_observed,
    )
    five = _parse_optional_strict_nonneg_int(
        _require(d, "complete_five_groups", f"{path}.complete_five_groups"),
        path=f"{path}.complete_five_groups",
    )
    remainder = _parse_optional_strict_nonneg_int(
        _require(d, "remainder_strokes", f"{path}.remainder_strokes"),
        path=f"{path}.remainder_strokes",
    )
    confidence = _map_confidence(d.get("confidence"), path=f"{path}.confidence")
    notes = _optional_str(d.get("notes"), path=f"{path}.notes")

    raw_components = d.get("components") or []
    if not isinstance(raw_components, list):
        raise VisionEvidenceContractError(f"{path}.components: リストである必要があります")
    components = [
        _parse_tally_component(c, path=f"{path}.components[{i}]")
        for i, c in enumerate(raw_components)
    ]

    # payloadにtally_countキーがあっても意図的に一切読み取らない（正本はPython側の再計算）。
    # 意味的な整合性（marks_present時のみ画数を持てる、components合計の一致等）はStep 2へ委譲する。
    return TallyEvidence(
        observation_status=observation_status,
        complete_five_groups=five,
        remainder_strokes=remainder,
        confidence=confidence,
        notes=notes,
        components=components,
    )


def _parse_store_code(
    d: Mapping[str, Any], *, path: str, allow_not_observed: bool
) -> StoreCodeEvidence:
    raw_value = _optional_str(
        _require(d, "raw_value", f"{path}.raw_value"), path=f"{path}.raw_value"
    )
    status = _map_evidence_status(
        _require(d, "status", f"{path}.status"),
        path=f"{path}.status",
        allow_not_observed=allow_not_observed,
    )
    confidence = _map_confidence(d.get("confidence"), path=f"{path}.confidence")
    notes = _optional_str(d.get("notes"), path=f"{path}.notes")

    # normalized_value・format_status（桁数チェック等）はこのStepではVisionに作らせない。
    # 正規化・近似探索・CSVマスター照合を行う将来のPython後処理の責務とする。
    return StoreCodeEvidence(
        raw_value=raw_value,
        normalized_value=None,
        status=status,
        confidence=confidence,
        format_status=StoreCodeFormatStatus.UNKNOWN,
        notes=notes,
    )


def _parse_cell_representation(
    d: Mapping[str, Any],
    *,
    path: str,
    allow_not_observed: bool,
    written_total: WrittenTotalEvidence,
) -> Optional[CellRepresentation]:
    """Step 3B v3で追加。cell_representationの要否は、旧JSON互換モード
    （allow_not_observed。not_observedの許可と同じフラグを流用する。両者とも
    「これは旧JSON移行・旧処理からのデータである」ことを表す点で意味が同じため）
    と written_total.status=not_applicable かどうかで決まる。

    - allow_not_observed=True（旧JSON互換）: 省略可。指定されていれば検証する。
    - written_total.status=not_applicable: この帳票版に項目自体が存在せず、
      分類対象のセルが無いため、指定されていた場合はむしろ契約違反として拒否する。
    - それ以外（通常モード）: 必須。

    値としての整合性（written_total/tallyの実際の状態との整合）はここでは判定せず、
    NumericFieldEvidence.__post_init__（Step 2）にそのまま委譲する
    （不整合の場合はEvidenceValidationErrorが送出される）。
    """
    raw = d.get("cell_representation")

    if allow_not_observed:
        if raw is None:
            return None
        return _map_enum(CellRepresentation, raw, path=f"{path}.cell_representation")

    if written_total.status == EvidenceStatus.NOT_APPLICABLE:
        if raw is not None:
            raise VisionEvidenceContractError(
                f"{path}.cell_representation: written_total.status=not_applicableの場合は"
                f"cell_representationを指定できません（分類対象のセル自体が存在しないため）: {raw!r}"
            )
        return None

    if raw is None:
        raise VisionEvidenceContractError(f"{path}.cell_representation: 必須キーが存在しません")
    return _map_enum(CellRepresentation, raw, path=f"{path}.cell_representation")


def _parse_numeric_field(
    d: Mapping[str, Any], *, path: str, allow_not_observed: bool
) -> NumericFieldEvidence:
    written_total = _parse_written_total(
        _require_mapping(d, "written_total", path),
        path=f"{path}.written_total",
        allow_not_observed=allow_not_observed,
    )
    tally = _parse_tally(
        _require_mapping(d, "tally", path),
        path=f"{path}.tally",
        allow_not_observed=allow_not_observed,
    )
    cell_representation = _parse_cell_representation(
        d, path=path, allow_not_observed=allow_not_observed, written_total=written_total
    )
    # written_total/tallyとcell_representationの意味的な整合性はStep 2へ委譲する
    # （不整合の組み合わせはEvidenceValidationErrorとして送出される）。
    return NumericFieldEvidence(
        written_total=written_total, tally=tally, cell_representation=cell_representation
    )


# ============================================================
# 公開関数
# ============================================================
def parse_vision_evidence_response(
    payload: Mapping[str, Any],
    *,
    expected_page_no: int,
    expected_form_version: str,
    selected_business_date: date,
    allow_not_observed: bool = False,
) -> PageEvidence:
    """Vision抽出結果のJSON(dict)をPageEvidenceへ変換する。

    Args:
        payload: Vision抽出結果のJSON契約に沿ったdict
            （docs記載の契約、およびvision_evidence_contract.EXAMPLE_VISION_EVIDENCE_PAYLOAD参照）。
        expected_page_no: 呼び出し側が既に把握している正本のページ番号。
            payload["page_no"]はこれと一致するかの照合対象に限定され、正本としては
            採用しない。
        expected_form_version: 呼び出し側が既に把握している正本の帳票版
            （例: P41/P59は"new"、P66は"old"）。store_code_resolution_source等から
            帳票版を推定してはならない。payload["form_version"]はこれと一致するかの
            照合対象に限定される。
        selected_business_date: 外部設定の正本となる営業日。payload内に日付らしき
            キーが含まれていても一切読み取らず、常にこの引数を採用する。
        allow_not_observed: Trueの場合のみ、payload中のstatus/observation_statusに
            not_observedを許可する（旧JSON互換データ向け）。デフォルトのFalseでは、
            現行のVision契約の通常出力としてnot_observedが現れた場合に
            VisionEvidenceContractErrorとする。

    Returns:
        PageEvidence。page_no/form_versionはexpected_page_no/expected_form_versionの値。

    Raises:
        VisionEvidenceContractError: 必須キー欠損、型不一致、未知のenum値、
            page_no/form_versionの不一致、許可されていないnot_observedの使用など、
            JSONの「形」が契約を満たさない場合。
        EvidenceValidationError: 値としては解釈できたが、Step 2の意味的な
            整合性チェック（marks_presentなのに画数がない等）に反する場合。
    """
    if not isinstance(payload, Mapping):
        raise VisionEvidenceContractError("payload全体がオブジェクト(dict)である必要があります")

    payload_page_no = _require(payload, "page_no", "page_no")
    if isinstance(payload_page_no, bool) or not isinstance(payload_page_no, int):
        raise VisionEvidenceContractError(f"page_no: 整数である必要があります: {payload_page_no!r}")
    if payload_page_no != expected_page_no:
        raise VisionEvidenceContractError(
            f"page_no: 既知のページ番号({expected_page_no})とpayloadの値"
            f"({payload_page_no})が一致しません"
        )

    payload_form_version = _require(payload, "form_version", "form_version")
    if not isinstance(payload_form_version, str) or not payload_form_version:
        raise VisionEvidenceContractError(
            f"form_version: 空でない文字列である必要があります: {payload_form_version!r}"
        )
    if payload_form_version != expected_form_version:
        raise VisionEvidenceContractError(
            f"form_version: 既知の帳票版({expected_form_version!r})とpayloadの値"
            f"({payload_form_version!r})が一致しません"
        )

    store_code_evidence = _parse_store_code(
        _require_mapping(payload, "store_code", "store_code"),
        path="store_code",
        allow_not_observed=allow_not_observed,
    )
    intro_evidence = _parse_numeric_field(
        _require_mapping(payload, "intro", "intro"),
        path="intro",
        allow_not_observed=allow_not_observed,
    )
    voice_evidence = _parse_numeric_field(
        _require_mapping(payload, "voice", "voice"),
        path="voice",
        allow_not_observed=allow_not_observed,
    )

    return PageEvidence(
        # page_no/form_versionは常にexpected_*（呼び出し側が持つ既知の正本）を採用する。
        # payload側の値は上記で照合のみに使い、正本としては採用しない。
        page_no=expected_page_no,
        form_version=expected_form_version,
        # payloadに営業日らしきキー(selected_business_date/business_date等)が含まれていても
        # 意図的に一切参照しない。常にこの引数のみを正本として使う。
        selected_business_date=selected_business_date.isoformat(),
        store_code_evidence=store_code_evidence,
        intro_evidence=intro_evidence,
        voice_evidence=voice_evidence,
    )


def parse_vision_evidence_response_with_audit(
    payload: Mapping[str, Any],
    *,
    expected_page_no: int,
    expected_form_version: str,
    selected_business_date: date,
    allow_not_observed: bool = False,
) -> VisionEvidenceAuditRecord:
    """parse_vision_evidence_responseと同じ変換を行い、生のpayloadおよび契約/プロンプトの
    バージョンも監査用に保持する。

    raw_payloadはPageEvidence（正本）には混ぜず、VisionEvidenceAuditRecordという
    別の器に保持する。通常の変換経路はparse_vision_evidence_response()のみで十分であり、
    この関数は監査ログ保存など生payloadが必要な呼び出し側向けの補助関数。
    """
    page_evidence = parse_vision_evidence_response(
        payload,
        expected_page_no=expected_page_no,
        expected_form_version=expected_form_version,
        selected_business_date=selected_business_date,
        allow_not_observed=allow_not_observed,
    )
    return VisionEvidenceAuditRecord(
        page_evidence=page_evidence,
        raw_payload=dict(payload),
        contract_version=VISION_EVIDENCE_CONTRACT_VERSION,
        prompt_version=VISION_EVIDENCE_PROMPT_VERSION,
    )
