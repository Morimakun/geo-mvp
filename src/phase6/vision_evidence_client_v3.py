"""Phase 6: Step 3B v3 Vision抽出クライアント（自動位置合わせ連動・合成画像対応）。

設計根拠: Step 3B v3実装指示（2026-07-25）。

v2（vision_evidence_client.py）との違い:
    - 実PDF（data/phase6_received/SFA用紙.pdf）に一切依存しない。呼び出し側が
      既にレンダリング済みのページ画像(PIL.Image)を渡す（PDFレンダリングは
      呼び出し側の責務。fitz/pymupdfはこのモジュールではimportしない）。
    - Vision APIを呼び出す前に必ず page_registration.register_page() による
      位置合わせを行い、RegistrationStatus.MATCHEDの場合のみVision APIを
      呼び出す。low_confidence/failedの場合はVisionを一切呼び出さず、
      RegistrationGateErrorを送出する（構造的な安全弁。呼び出し側の実装ミスに
      関わらず強制される。page_registration.resolve_regionsが既に持つ同種の
      ガードを、Vision呼び出しの手前でも重ねて適用する形になる）。
    - 同一セルをwritten用・tally用の別領域として二重送信しない。
      cell_id単位のcontext/detail画像（page_registration.CellRegionPair /
      StoreCodeRegionPair）を1組ずつ送る。
    - written/tallyに加えてcell_representationを含むStep 3B v3契約
      （vision_evidence_contract.VISION_EVIDENCE_CONTRACT_VERSION="2.0.0"）で
      レスポンスをパースする。
    - Vision応答の各証拠グループ（intro/voice/store_code）にcell_idを
      自己申告させ、送信していないcell_idを参照した場合はVisionEvidenceContractError
      として拒否する（v2のregion_id自己申告・検証の仕組みを、Part Cでのセル単位への
      統合に合わせて簡略化したもの）。

このモジュールでは実装しないもの（v2と同様のスコープ外、加えて今回の簡略化）:
    - CSV resolverとの結合・三者比較・review routing・UI・Gmail連携。
    - PDFファイルの読み込み・SHA-256検証（v2のverify_source_pdf/SOURCE_PDF_PATHは
      このモジュールでは使わない。画像はすでに呼び出し側が用意している前提）。
    - 一時的APIエラー・契約違反時の再試行ループ（v2はMAX_RETRIES=1で1回再試行するが、
      このv3初版では単純化のため1attemptのみとする。attempt単位の監査記録の形は
      v2を踏襲するため、再試行を追加する場合もaudit構造の変更は不要）。
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

import anthropic
from PIL import Image

from src.phase6.evidence_schema import EvidenceValidationError
from src.phase6.page_registration import (
    AnchorTemplate,
    CellRegionPair,
    RegistrationResult,
    RegistrationStatus,
    StoreCodeRegionPair,
    register_page,
    resolve_cell_region_pair,
)
from src.phase6.vision_evidence_contract import (
    VISION_EVIDENCE_CONTRACT_VERSION,
    VisionEvidenceContractError,
)
from src.phase6.vision_evidence_parser import parse_vision_evidence_response
from src.phase6.vision_evidence_prompt import (
    VISION_EVIDENCE_PROMPT_VERSION,
    build_cell_scoped_prompt_v3,
)

__all__ = [
    "VISION_MODEL_V3",
    "VISION_MAX_TOKENS_V3",
    "RegistrationGateError",
    "VisionApiCallErrorV3",
    "run_vision_evidence_pilot_page_v3",
]


VISION_MODEL_V3 = "claude-sonnet-5"
VISION_MAX_TOKENS_V3 = 2048
_VISION_TOOL_NAME_V3 = "submit_vision_evidence_v3"

_KNOWN_CELL_GROUPS = ("intro", "voice", "store_code")


class RegistrationGateError(Exception):
    """位置合わせがRegistrationStatus.MATCHEDでないため、Vision APIを呼び出さずに
    処理を中断したことを表す。self.registrationに位置合わせ結果を保持する。"""

    def __init__(self, message: str, *, registration: RegistrationResult) -> None:
        super().__init__(message)
        self.registration = registration


class VisionApiCallErrorV3(Exception):
    """Vision APIレスポンスの取得・tool_use抽出に失敗した場合に送出する
    （契約違反ではなく、レスポンス自体が壊れている場合）。"""


# ============================================================
# ヘルパー: 画像クロップ・ハッシュ
# ============================================================
def _crop_image(image: "Image.Image", region) -> "Image.Image":
    return image.crop((region.x, region.y, region.x + region.width, region.y + region.height))


def _image_to_jpeg_bytes(image: "Image.Image") -> bytes:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ============================================================
# Vision tool定義（Step 3B v3契約: cell_representation + cell_id自己申告）
# ============================================================
def _written_total_schema_v3() -> dict:
    return {
        "type": "object",
        "required": ["value", "status", "confidence", "notes"],
        "properties": {
            "value": {"type": ["integer", "null"]},
            "status": {
                "type": "string",
                "enum": ["observed", "no_value", "unreadable", "not_applicable"],
            },
            "confidence": {"type": ["string", "null"], "enum": ["high", "medium", "low", None]},
            "notes": {"type": "string", "maxLength": 160},
        },
        "additionalProperties": False,
    }


def _tally_component_schema_v3() -> dict:
    return {
        "type": "object",
        "required": ["row_label", "complete_five_groups", "remainder_strokes"],
        "properties": {
            "row_label": {"type": ["string", "null"]},
            "complete_five_groups": {"type": "integer", "minimum": 0},
            "remainder_strokes": {"type": "integer", "minimum": 0, "maximum": 4},
        },
        "additionalProperties": False,
    }


def _tally_schema_v3() -> dict:
    return {
        "type": "object",
        "required": [
            "observation_status",
            "complete_five_groups",
            "remainder_strokes",
            "confidence",
            "notes",
            "components",
        ],
        "properties": {
            "observation_status": {
                "type": "string",
                "enum": ["marks_present", "no_marks_observed", "unreadable", "not_applicable"],
            },
            "complete_five_groups": {"type": ["integer", "null"], "minimum": 0},
            "remainder_strokes": {"type": ["integer", "null"], "minimum": 0, "maximum": 4},
            "confidence": {"type": ["string", "null"], "enum": ["high", "medium", "low", None]},
            "notes": {"type": "string", "maxLength": 160},
            "components": {"type": "array", "items": _tally_component_schema_v3(), "maxItems": 8},
        },
        "additionalProperties": False,
    }


def _numeric_field_schema_v3() -> dict:
    return {
        "type": "object",
        "required": ["written_total", "tally", "cell_representation", "cell_id"],
        "properties": {
            "written_total": _written_total_schema_v3(),
            "tally": _tally_schema_v3(),
            "cell_representation": {
                "type": "string",
                "enum": ["numeric", "tally", "blank", "unreadable", "mixed"],
            },
            "cell_id": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _store_code_schema_v3() -> dict:
    return {
        "type": "object",
        "required": ["raw_value", "status", "confidence", "notes", "cell_id"],
        "properties": {
            "raw_value": {"type": ["string", "null"]},
            "status": {
                "type": "string",
                "enum": ["observed", "no_value", "unreadable", "not_applicable"],
            },
            "confidence": {"type": ["string", "null"], "enum": ["high", "medium", "low", None]},
            "notes": {"type": "string", "maxLength": 160},
            "cell_id": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _build_tool_definition_v3(*, include_store_code: bool) -> dict:
    properties = {
        "page_no": {"type": "integer"},
        "form_version": {"type": "string", "enum": ["new", "old"]},
        "intro": _numeric_field_schema_v3(),
        "voice": _numeric_field_schema_v3(),
    }
    required = ["page_no", "form_version", "intro", "voice"]
    if include_store_code:
        properties["store_code"] = _store_code_schema_v3()
        required.append("store_code")
    return {
        "name": _VISION_TOOL_NAME_V3,
        "description": (
            "帳票画像のセル単位クロップから抽出した店舗コード・紹介/お声がけの証拠を、"
            "この契約の形で送信する。"
        ),
        "input_schema": {
            "type": "object",
            "required": required,
            "properties": properties,
            "additionalProperties": False,
        },
    }


def _build_content_blocks_v3(images: list, prompt_text: str) -> list:
    blocks = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(image_bytes).decode("ascii"),
            },
        }
        for _label, image_bytes in images
    ]
    blocks.append({"type": "text", "text": prompt_text})
    return blocks


def _call_vision_api_once_v3(
    client: "anthropic.Anthropic", images: list, prompt_text: str, tool: dict
):
    content = _build_content_blocks_v3(images, prompt_text)
    assert VISION_MAX_TOKENS_V3 <= 2048, "max_tokensは2048以下である必要があります（契約上の制約）"
    return client.messages.create(
        model=VISION_MODEL_V3,
        max_tokens=VISION_MAX_TOKENS_V3,
        tools=[tool],
        tool_choice={"type": "tool", "name": _VISION_TOOL_NAME_V3},
        messages=[{"role": "user", "content": content}],
    )


def _extract_tool_input_v3(message: Any) -> dict:
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == _VISION_TOOL_NAME_V3:
            payload = block.input
            if not isinstance(payload, dict):
                raise VisionApiCallErrorV3("tool_useブロックのinputがオブジェクト(dict)ではありません")
            return payload
    raise VisionApiCallErrorV3(
        f"Vision応答に{_VISION_TOOL_NAME_V3}のtool_useブロックが見つかりません"
    )


def _usage_to_dict(message: Any) -> Optional[dict]:
    usage = getattr(message, "usage", None)
    if usage is None:
        return None
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }


def _validate_cell_attribution(payload: dict, sent_cell_ids: set) -> None:
    """各証拠グループ（intro/voice/store_code）が自己申告したcell_idが、実際に
    送信したcell_id集合に含まれる（かつそのグループ自身のcell_idと一致する）ことを
    検証する。送っていないセルを参照している場合はVisionEvidenceContractErrorとする。"""
    for group_name in _KNOWN_CELL_GROUPS:
        if group_name not in sent_cell_ids:
            continue  # このページではそもそも送っていないグループ（例: 旧帳票のstore_code）
        node = payload.get(group_name)
        if not isinstance(node, dict):
            continue  # 必須キー欠損自体は後続のparse_vision_evidence_responseが検出する
        cell_id = node.get("cell_id")
        if cell_id != group_name:
            raise VisionEvidenceContractError(
                f"{group_name}.cell_id: 送信していないセル{cell_id!r}を参照しています"
                f"（送信済みcell_id: {sorted(sent_cell_ids)}）"
            )


# ============================================================
# 1ページ分のパイロット実行（v3 / 単一attempt・登録ゲート付き）
# ============================================================
def run_vision_evidence_pilot_page_v3(
    client: "anthropic.Anthropic",
    *,
    run_id: str,
    page_no: int,
    expected_form_version: str,
    selected_business_date: date,
    target_image: "Image.Image",
    anchor_template: AnchorTemplate,
    cell_region_pairs: dict,
    store_code_region_pair: Optional[StoreCodeRegionPair] = None,
    output_dir: Path,
    registration_kwargs: Optional[dict] = None,
) -> dict:
    """1ページ分のVision抽出パイロット（v3）を実行し、監査記録(dict)を返す。

    Args:
        target_image: 既にレンダリング済みのページ画像。このモジュールはPDFを
            読み込まない（呼び出し側の責務）。
        anchor_template: page_registration.extract_anchor_templateで作成した
            基準テンプレート。
        cell_region_pairs: {"intro": CellRegionPair, "voice": CellRegionPair}
            のような、cell_id -> CellRegionPairの対応表。
        store_code_region_pair: 店舗コード欄がある帳票版でのみ指定する
            （旧帳票のように欄自体が存在しない場合はNone）。

    位置合わせ(register_page)がRegistrationStatus.MATCHEDでない場合は、
    Vision APIを一切呼び出さずにRegistrationGateErrorを送出する
    （raiseする前に、位置合わせ結果を含む監査記録は保存する）。

    APIキー・画像base64本体は監査記録に一切含めない（image_sha256_listのみ保持）。
    """
    registration = register_page(anchor_template, target_image, **(registration_kwargs or {}))

    run_dir = output_dir / run_id
    audit: dict = {
        "run_id": run_id,
        "page_no": page_no,
        "expected_form_version": expected_form_version,
        "selected_business_date": selected_business_date.isoformat(),
        "contract_version": VISION_EVIDENCE_CONTRACT_VERSION,
        "prompt_version": VISION_EVIDENCE_PROMPT_VERSION,
        "model": VISION_MODEL_V3,
        "max_tokens": VISION_MAX_TOKENS_V3,
        "registration": registration.to_dict(),
        "success": False,
        "attempt_count": 0,
        "page_evidence": None,
        "attempts": [],
    }

    def _finalize() -> dict:
        audit_dir = run_dir / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_path = audit_dir / f"p{page_no:02d}_audit.json"
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        return audit

    if registration.status != RegistrationStatus.MATCHED:
        _finalize()
        raise RegistrationGateError(
            f"page_no={page_no}: registration.status={registration.status.value!r}のため"
            f"Vision APIを呼び出さずに中断しました（score={registration.score:.4f}, "
            f"basis={registration.basis}）",
            registration=registration,
        )

    image_width, image_height = target_image.size

    # cell_id単位でcontext/detail画像を解決・クロップする（PDF再読込は行わない）。
    images: list = []  # (label, jpeg_bytes)
    for cell_id, pair in cell_region_pairs.items():
        context, detail = resolve_cell_region_pair(
            pair, registration, image_width=image_width, image_height=image_height
        )
        images.append((f"{cell_id}__context", _image_to_jpeg_bytes(_crop_image(target_image, context))))
        images.append((f"{cell_id}__detail", _image_to_jpeg_bytes(_crop_image(target_image, detail))))

    include_store_code = store_code_region_pair is not None
    if include_store_code:
        context, detail = resolve_cell_region_pair(
            store_code_region_pair,
            registration,
            image_width=image_width,
            image_height=image_height,
        )
        images.append(("store_code__context", _image_to_jpeg_bytes(_crop_image(target_image, context))))
        images.append(("store_code__detail", _image_to_jpeg_bytes(_crop_image(target_image, detail))))

    sent_cell_ids = set(cell_region_pairs.keys())
    if include_store_code:
        sent_cell_ids.add("store_code")

    prompt_text = build_cell_scoped_prompt_v3(
        page_no=page_no,
        form_version=expected_form_version,
        cell_ids_in_order=list(cell_region_pairs.keys()) + (["store_code"] if include_store_code else []),
    )
    tool = _build_tool_definition_v3(include_store_code=include_store_code)

    image_sha256_list = [_sha256_bytes(image_bytes) for _label, image_bytes in images]

    attempt_record: dict = {
        "attempt_number": 1,
        "request_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "success": False,
        "error_type": None,
        "error_message": None,
        "raw_response_text": None,
        "parsed_payload": None,
        "input_tokens": None,
        "output_tokens": None,
        "stop_reason": None,
        "model": VISION_MODEL_V3,
        "prompt_version": VISION_EVIDENCE_PROMPT_VERSION,
        "contract_version": VISION_EVIDENCE_CONTRACT_VERSION,
        "image_sha256_list": image_sha256_list,
    }
    audit["attempt_count"] = 1

    try:
        message = _call_vision_api_once_v3(client, images, prompt_text, tool)
    except anthropic.AnthropicError as exc:
        attempt_record["error_type"] = type(exc).__name__
        attempt_record["error_message"] = str(exc)
        audit["attempts"].append(attempt_record)
        return _finalize()

    attempt_record["stop_reason"] = getattr(message, "stop_reason", None)
    usage = _usage_to_dict(message)
    if usage:
        attempt_record["input_tokens"] = usage.get("input_tokens")
        attempt_record["output_tokens"] = usage.get("output_tokens")

    try:
        payload = _extract_tool_input_v3(message)
        attempt_record["raw_response_text"] = json.dumps(payload, ensure_ascii=False)
        attempt_record["parsed_payload"] = payload

        _validate_cell_attribution(payload, sent_cell_ids)

        page_evidence = parse_vision_evidence_response(
            payload,
            expected_page_no=page_no,
            expected_form_version=expected_form_version,
            selected_business_date=selected_business_date,
        )
    except (VisionApiCallErrorV3, VisionEvidenceContractError, EvidenceValidationError) as exc:
        attempt_record["error_type"] = type(exc).__name__
        attempt_record["error_message"] = str(exc)
        audit["attempts"].append(attempt_record)
        return _finalize()

    attempt_record["success"] = True
    audit["attempts"].append(attempt_record)
    audit["success"] = True
    audit["page_evidence"] = page_evidence.to_dict(include_legacy=True)
    return _finalize()
