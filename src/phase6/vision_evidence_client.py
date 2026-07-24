"""Phase 6: 実画像Vision抽出クライアント（Step 3B / vision evidence client）。

設計根拠: docs/PHASE_6_TRIPLE_EVIDENCE_SCHEMA_DESIGN_REVIEW.md 第4版
         および Step 3B実装指示（2026-07-23）、Step 3B v1パイロット後の修正指示（2026-07-23）

このモジュールの責務は「Step 3Aで確定した契約・パーサーを、実際のSFA用紙.pdfの
帳票版ごとに固定した対象領域（region）画像へ接続し、tool use（構造化出力）で
Vision APIを呼び出し、attempt単位で監査可能な記録として保存する」ことに限定される。

このStepでは実装しないもの:
    - CSV resolver（Step 1）との結合
    - 三者比較・review routing・UI・Gmail連携
    - phase6_stage3_full.pyへの直接追記（このモジュールはそれを一切import/変更しない）
    - 66ページ一括処理（対象はP32/P41/P59/P66の4ページのみ）
    - GT・Excel原本・検証HTMLの変更

v1パイロット（run_id=step3b_pilot_v1）からの主な変更点:
    1. run_idごとに出力ディレクトリを分け、既存run_idの結果を上書きしない。
    2. 最終試行だけでなく、全attemptを保存する（成功しても過去の失敗attemptを消さない）。
    3. フルページ画像を主入力にせず、帳票版ごとに固定した対象領域（NEW_FORM_REGIONS/
       OLD_FORM_REGIONS）のクロップ画像のみを渡す。座標はv1パイロットで実際に誤検出が
       発生した箇所（【内訳】セクションの個別行）を含まないよう、PDFのラスタ画像を
       目視して帳票レイアウト・項目ラベルの罫線位置を基準に固定した（結果を見てからの
       事後調整はしていない）。
    4. Vision応答の各証拠にregion_idを自己申告させ、送信していない領域IDを参照した
       場合はVisionEvidenceContractErrorとして拒否する。
    5. Anthropicの tool use（構造化出力）を使用し、自由文・マークダウンコードフェンスを
       禁止する。新しい外部依存は追加していない（既存のanthropicパッケージの機能）。
    6. max_tokens を8192から2048へ縮小した。

プリフライトで固定した値（2026-07-23実測。API呼び出し前にコードへ固定 - ユーザー指示）:
    - 元PDFパス: data/phase6_received/SFA用紙.pdf
    - ファイル名: SFA用紙.pdf
    - SHA-256: SOURCE_PDF_SHA256（下記）
    - 総ページ数: 66
    実行時に再計算したSHA-256がこの値と一致しない場合はSourcePdfMismatchErrorを送出し、
    無断でのファイル差し替え（別PDF・過去の監査用画像の混入）を防ぐ。
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
import fitz
from PIL import Image, ImageDraw

from src.phase6.evidence_schema import EvidenceValidationError
from src.phase6.vision_evidence_contract import (
    VISION_EVIDENCE_CONTRACT_VERSION,
    VisionEvidenceContractError,
)
from src.phase6.vision_evidence_parser import parse_vision_evidence_response
from src.phase6.vision_evidence_prompt import (
    VISION_EVIDENCE_PROMPT_VERSION,
    build_region_scoped_prompt,
)

__all__ = [
    "SOURCE_PDF_PATH",
    "SOURCE_PDF_FILENAME",
    "SOURCE_PDF_SHA256",
    "SOURCE_PDF_TOTAL_PAGES",
    "VISION_MODEL",
    "VISION_MAX_TOKENS",
    "MAX_RETRIES",
    "SourcePdfMismatchError",
    "VisionApiCallError",
    "CropRegion",
    "RenderedImage",
    "NEW_FORM_REGIONS",
    "OLD_FORM_REGIONS",
    "PAGE_REGION_OVERRIDES",
    "regions_for_form_version",
    "regions_for_page",
    "pdf_page_to_index",
    "verify_source_pdf",
    "render_region_crop",
    "build_crop_manifest",
    "build_contact_sheet",
    "run_vision_evidence_pilot_page",
]


# ============================================================
# プリフライトで確定した定数
# ============================================================
SOURCE_PDF_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "phase6_received" / "SFA用紙.pdf"
SOURCE_PDF_FILENAME = "SFA用紙.pdf"
SOURCE_PDF_SHA256 = "a744a398f5262ba31e5220721014358f9c236d718e01ac492b796b18dc0ed174"
SOURCE_PDF_TOTAL_PAGES = 66

VISION_MODEL = "claude-sonnet-5"
VISION_MAX_TOKENS = 2048
VISION_TOOL_NAME = "submit_vision_evidence"

MAX_RETRIES = 1  # 契約違反・JSON破損・一時的APIエラーのみ最大1回再試行

_TRANSIENT_API_ERRORS = (
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.RateLimitError,
    anthropic.InternalServerError,
)


class SourcePdfMismatchError(Exception):
    """実行時の元PDFがプリフライトで固定した値（ファイル名・SHA-256）と一致しない場合に送出する。"""


class VisionApiCallError(Exception):
    """Vision APIレスポンスの取得・tool_use抽出に失敗した場合に送出する
    （契約違反ではなく、レスポンス自体が壊れている場合）。"""


# ============================================================
# 帳票版ごとの固定対象領域（region）
# 座標はPDFポイント。P32(新)/P66(旧)の実画像をラスタ描画して目視し、
# 罫線・項目ラベルの位置を基準に決定した（結果を見てからの事後調整はしていない）。
# 新帳票の紹介written_total/紹介tallyは同一セル（【案件】合計行の紹介列）を指す
# （実画像を確認した結果、正の字専用の別記入欄が存在しないため。声掛も同様）。
# ============================================================
@dataclass(frozen=True)
class CropRegion:
    region_id: str
    x0_pt: float
    y0_pt: float
    x1_pt: float
    y1_pt: float


# 発見事項（重要）: P32を基準に測定した座標をP41/P59へそのまま流用したところ、
# store_code_region・summary行ともに約30〜45pt下にずれて写り込んだ（P41/P59は
# store_code欄・案件合計行の垂直位置がP32よりも下側にある）。X座標（列位置）は
# 3ページとも一致していたため、スキャン時の紙送り・位置合わせのばらつきにより
# 縦方向のみページごとに数十pt単位でずれることが判明した。
# そのため「帳票版ごとに1組の絶対座標」だけでは対象領域を安定して捉えられず、
# 実在するP32/P41/P59それぞれの画像を目視し、罫線・項目ラベルの位置を基準に
# ページ単位で座標を確定した（値を見てからの事後調整ではなく、層版の印字位置の
# 実測によるもの）。以下がform_version単位のデフォルト値（主にP32を基準）、
# その下のPAGE_REGION_OVERRIDESが個別ページの実測値。
NEW_FORM_REGIONS = {
    # AU1K印刷済み接頭辞 + 手書き7桁ボックス（P32実測）
    "store_code_region": CropRegion("store_code_region", 15, 44, 265, 72),
    # 【案件】合計行（項番5）紹介列セル（P32実測。列境界を精密プローブで再確認済み）
    "intro_written_total_region": CropRegion("intro_written_total_region", 160, 182, 215, 213),
    "intro_tally_region": CropRegion("intro_tally_region", 160, 182, 215, 213),
    # 【案件】合計行（項番5）声掛列セル（P32実測）
    "voice_written_total_region": CropRegion("voice_written_total_region", 215, 182, 243, 213),
    "voice_tally_region": CropRegion("voice_tally_region", 215, 182, 243, 213),
}

OLD_FORM_REGIONS = {
    # 旧帳票には店舗コード欄自体が存在しないためstore_code_regionはなし。
    # 【案件】合計行紹介列セル（P66実測。文字が枠上部にはみ出す筆致だったため上方向に余白を追加）
    "intro_written_total_region": CropRegion("intro_written_total_region", 138, 130, 190, 188),
    "intro_tally_region": CropRegion("intro_tally_region", 138, 130, 190, 188),
    # 【案件】合計行声掛列セル（P66実測）
    "voice_written_total_region": CropRegion("voice_written_total_region", 190, 130, 228, 188),
    "voice_tally_region": CropRegion("voice_tally_region", 190, 130, 228, 188),
}

# ページ個別の実測値（縦方向のスキャン registration ずれに対応するための上書き）。
# X座標（列位置）は3ページで一致していたためNEW_FORM_REGIONSと共通のまま。
PAGE_REGION_OVERRIDES = {
    41: {
        "store_code_region": CropRegion("store_code_region", 15, 70, 280, 102),
        "intro_written_total_region": CropRegion("intro_written_total_region", 160, 214, 215, 245),
        "intro_tally_region": CropRegion("intro_tally_region", 160, 214, 215, 245),
        "voice_written_total_region": CropRegion("voice_written_total_region", 215, 214, 243, 245),
        "voice_tally_region": CropRegion("voice_tally_region", 215, 214, 243, 245),
    },
    59: {
        "store_code_region": CropRegion("store_code_region", 15, 70, 280, 102),
        "intro_written_total_region": CropRegion("intro_written_total_region", 160, 218, 215, 249),
        "intro_tally_region": CropRegion("intro_tally_region", 160, 218, 215, 249),
        "voice_written_total_region": CropRegion("voice_written_total_region", 215, 218, 243, 249),
        "voice_tally_region": CropRegion("voice_tally_region", 215, 218, 243, 249),
    },
}

REGION_RENDER_SCALE = 8  # 対象領域が小さいため高倍率で描画し可読性を確保する


def regions_for_form_version(form_version: str) -> dict:
    if form_version == "new":
        return NEW_FORM_REGIONS
    if form_version == "old":
        return OLD_FORM_REGIONS
    raise ValueError(f"未知のform_versionです: {form_version!r}")


def regions_for_page(pdf_page_no: int, form_version: str) -> dict:
    """指定ページの対象領域を返す。PAGE_REGION_OVERRIDESに実測値があればそれを優先し、
    なければform_version単位のデフォルト値にフォールバックする。"""
    base = dict(regions_for_form_version(form_version))
    base.update(PAGE_REGION_OVERRIDES.get(pdf_page_no, {}))
    return base


# 各証拠がどのregion_idを参照してよいかの対応表（region_id自己申告の検証に使う）。
_EVIDENCE_REGION_FIELD_PATHS = {
    "store_code_region": (("store_code",),),
    "intro_written_total_region": (("intro", "written_total"),),
    "intro_tally_region": (("intro", "tally"),),
    "voice_written_total_region": (("voice", "written_total"),),
    "voice_tally_region": (("voice", "tally"),),
}


@dataclass(frozen=True)
class RenderedImage:
    label: str
    image_bytes: bytes
    sha256: str
    width: int
    height: int
    image_format: str
    render_scale: float
    source_region_pt: Optional[dict]

    def to_manifest_dict(self, *, filename: str) -> dict:
        """image_bytesを含まない、監査記録・crop manifest用の安全な辞書表現。"""
        return {
            "region_id": self.label,
            "filename": filename,
            "sha256": self.sha256,
            "width": self.width,
            "height": self.height,
            "format": self.image_format,
            "render_scale": self.render_scale,
            "source_region_pt": self.source_region_pt,
        }


# ============================================================
# ヘルパー: ハッシュ・PDF検証
# ============================================================
def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_source_pdf() -> None:
    """元PDFのファイル名・SHA-256がプリフライトで固定した値と一致することを確認する。"""
    if not SOURCE_PDF_PATH.exists():
        raise SourcePdfMismatchError(f"元PDFが見つかりません: {SOURCE_PDF_PATH}")
    if SOURCE_PDF_PATH.name != SOURCE_PDF_FILENAME:
        raise SourcePdfMismatchError(
            f"ファイル名が一致しません: expected={SOURCE_PDF_FILENAME!r}, actual={SOURCE_PDF_PATH.name!r}"
        )
    actual_sha256 = _sha256_file(SOURCE_PDF_PATH)
    if actual_sha256 != SOURCE_PDF_SHA256:
        raise SourcePdfMismatchError(
            "元PDFのSHA-256が一致しません（差し替えの可能性があるため停止）: "
            f"expected={SOURCE_PDF_SHA256}, actual={actual_sha256}"
        )


def pdf_page_to_index(pdf_page_no: int) -> int:
    """PDF上の1始まりページ番号を、PyMuPDFの0始まりインデックスへ変換する。"""
    if pdf_page_no < 1:
        raise ValueError(f"pdf_page_noは1以上である必要があります: {pdf_page_no}")
    if pdf_page_no > SOURCE_PDF_TOTAL_PAGES:
        raise ValueError(
            f"pdf_page_noが元PDFの総ページ数({SOURCE_PDF_TOTAL_PAGES})を超えています: {pdf_page_no}"
        )
    return pdf_page_no - 1


# ============================================================
# 画像レンダリング（固定対象領域のみ。フルページは描画しない）
# ============================================================
def render_region_crop(
    pdf_page_no: int, region: CropRegion, *, scale: float = REGION_RENDER_SCALE
) -> RenderedImage:
    verify_source_pdf()
    doc = fitz.open(str(SOURCE_PDF_PATH))
    try:
        page = doc[pdf_page_to_index(pdf_page_no)]
        rect = fitz.Rect(region.x0_pt, region.y0_pt, region.x1_pt, region.y1_pt)
        pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=92)
        image_bytes = buf.getvalue()
        width, height = img.width, img.height
    finally:
        doc.close()
    return RenderedImage(
        label=region.region_id,
        image_bytes=image_bytes,
        sha256=_sha256_bytes(image_bytes),
        width=width,
        height=height,
        image_format="JPEG",
        render_scale=scale,
        source_region_pt={
            "x0_pt": region.x0_pt,
            "y0_pt": region.y0_pt,
            "x1_pt": region.x1_pt,
            "y1_pt": region.y1_pt,
        },
    )


def build_crop_manifest(
    pdf_page_no: int, form_version: str, *, images_dir: Path
) -> tuple:
    """指定ページの全region画像をレンダリング・保存し、(RenderedImageのリスト, manifest記録のリスト)を返す。
    imagesの順序がそのままVisionへ渡す画像の順序・プロンプトのregion_id対応表の順序になる。
    """
    regions = regions_for_page(pdf_page_no, form_version)
    images_dir.mkdir(parents=True, exist_ok=True)
    images: list = []
    manifest: list = []
    for region_id in sorted(regions):  # region_idの辞書順で固定（実行のたびに順序が変わらないようにする）
        region = regions[region_id]
        img = render_region_crop(pdf_page_no, region)
        filename = f"p{pdf_page_no:02d}_{region_id}.jpg"
        (images_dir / filename).write_bytes(img.image_bytes)
        images.append(img)
        manifest.append(img.to_manifest_dict(filename=filename))
    return images, manifest


def build_contact_sheet(
    pages: list,
    *,
    output_path: Path,
    thumb_scale: float = 3.0,
) -> Path:
    """複数ページ分のregionクロップを1枚のcontact sheet画像にまとめて保存する。
    API呼び出し前に目視確認するためのもの（Vision APIへは渡さない）。

    Args:
        pages: [{"pdf_page_no": int, "form_version": str}, ...]
    """
    cells = []  # (label_text, PIL.Image)
    for spec in pages:
        pdf_page_no = spec["pdf_page_no"]
        form_version = spec["form_version"]
        regions = regions_for_page(pdf_page_no, form_version)
        for region_id in sorted(regions):
            region = regions[region_id]
            rendered = render_region_crop(pdf_page_no, region, scale=thumb_scale)
            img = Image.open(io.BytesIO(rendered.image_bytes))
            cells.append((f"P{pdf_page_no} [{form_version}] {region_id}", img))

    if not cells:
        raise ValueError("contact sheetを作るクロップがありません")

    label_h = 18
    pad = 6
    cell_w = max(img.width for _, img in cells) + pad * 2
    cell_h = max(img.height for _, img in cells) + label_h + pad * 2
    cols = 5
    rows = (len(cells) + cols - 1) // cols

    sheet = Image.new("RGB", (cell_w * cols, cell_h * rows), (255, 255, 255))
    draw = ImageDraw.Draw(sheet)
    for i, (label, img) in enumerate(cells):
        col, row = i % cols, i // cols
        x0, y0 = col * cell_w, row * cell_h
        draw.text((x0 + pad, y0 + 2), label, fill=(0, 0, 0))
        sheet.paste(img, (x0 + pad, y0 + label_h + pad))
        draw.rectangle(
            [x0 + 1, y0 + 1, x0 + cell_w - 2, y0 + cell_h - 2], outline=(200, 200, 200)
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, format="JPEG", quality=90)
    return output_path


# ============================================================
# Vision API 呼び出し（tool use / 構造化出力）
# ============================================================
def _written_total_schema() -> dict:
    return {
        "type": "object",
        "required": ["value", "status", "confidence", "notes", "region_id"],
        "properties": {
            "value": {"type": ["integer", "null"]},
            "status": {
                "type": "string",
                "enum": ["observed", "no_value", "unreadable", "not_applicable"],
            },
            "confidence": {"type": ["string", "null"], "enum": ["high", "medium", "low", None]},
            "notes": {"type": "string", "maxLength": 160},
            "region_id": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _tally_component_schema() -> dict:
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


def _tally_schema() -> dict:
    return {
        "type": "object",
        "required": [
            "observation_status",
            "complete_five_groups",
            "remainder_strokes",
            "confidence",
            "notes",
            "components",
            "region_id",
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
            "components": {"type": "array", "items": _tally_component_schema(), "maxItems": 8},
            "region_id": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _store_code_schema() -> dict:
    return {
        "type": "object",
        "required": ["raw_value", "status", "confidence", "notes", "region_id"],
        "properties": {
            "raw_value": {"type": ["string", "null"]},
            "status": {
                "type": "string",
                "enum": ["observed", "no_value", "unreadable", "not_applicable"],
            },
            "confidence": {"type": ["string", "null"], "enum": ["high", "medium", "low", None]},
            "notes": {"type": "string", "maxLength": 160},
            "region_id": {"type": "string"},
        },
        "additionalProperties": False,
    }


def _numeric_field_schema() -> dict:
    return {
        "type": "object",
        "required": ["written_total", "tally"],
        "properties": {"written_total": _written_total_schema(), "tally": _tally_schema()},
        "additionalProperties": False,
    }


def _build_tool_definition(*, include_store_code: bool) -> dict:
    properties = {
        "page_no": {"type": "integer"},
        "form_version": {"type": "string", "enum": ["new", "old"]},
        "intro": _numeric_field_schema(),
        "voice": _numeric_field_schema(),
    }
    required = ["page_no", "form_version", "intro", "voice"]
    if include_store_code:
        properties["store_code"] = _store_code_schema()
        required.append("store_code")
    return {
        "name": VISION_TOOL_NAME,
        "description": "帳票画像から抽出した店舗コード・紹介/お声がけの数字欄・正の字の証拠を、この契約の形で送信する。",
        "input_schema": {
            "type": "object",
            "required": required,
            "properties": properties,
            "additionalProperties": False,
        },
    }


def _build_content_blocks(images: list, prompt_text: str) -> list:
    blocks = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.b64encode(img.image_bytes).decode("ascii"),
            },
        }
        for img in images
    ]
    blocks.append({"type": "text", "text": prompt_text})
    return blocks


def _call_vision_api_once(
    client: "anthropic.Anthropic",
    images: list,
    prompt_text: str,
    *,
    include_store_code: bool,
):
    content = _build_content_blocks(images, prompt_text)
    tool = _build_tool_definition(include_store_code=include_store_code)
    assert VISION_MAX_TOKENS <= 2048, "max_tokensは2048以下である必要があります（契約上の制約）"
    return client.messages.create(
        model=VISION_MODEL,
        max_tokens=VISION_MAX_TOKENS,
        tools=[tool],
        tool_choice={"type": "tool", "name": VISION_TOOL_NAME},
        messages=[{"role": "user", "content": content}],
    )


def _extract_tool_input(message: Any) -> dict:
    for block in message.content:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == VISION_TOOL_NAME:
            payload = block.input
            if not isinstance(payload, dict):
                raise VisionApiCallError("tool_useブロックのinputがオブジェクト(dict)ではありません")
            return payload
    raise VisionApiCallError(
        f"Vision応答に{VISION_TOOL_NAME}のtool_useブロックが見つかりません"
    )


def _usage_to_dict(message: Any) -> Optional[dict]:
    usage = getattr(message, "usage", None)
    if usage is None:
        return None
    return {
        "input_tokens": getattr(usage, "input_tokens", None),
        "output_tokens": getattr(usage, "output_tokens", None),
    }


def _validate_region_attribution(payload: dict, allowed_region_ids: set) -> None:
    """各証拠のregion_idが、実際に送信した画像のregion_id集合に含まれることを検証する。
    送っていない領域を参照している場合はVisionEvidenceContractErrorとする。"""
    for expected_region_id, field_paths in _EVIDENCE_REGION_FIELD_PATHS.items():
        if expected_region_id not in allowed_region_ids:
            continue  # このページではそもそも送っていない領域（例: 旧帳票のstore_code）
        for path in field_paths:
            node: Any = payload
            path_str = ".".join(path)
            for key in path:
                if not isinstance(node, dict) or key not in node:
                    # 必須キー欠損自体は後続のparse_vision_evidence_responseが検出するため、
                    # ここでは region_id 検証をスキップする。
                    node = None
                    break
                node = node[key]
            if not isinstance(node, dict):
                continue
            region_id = node.get("region_id")
            if region_id not in allowed_region_ids:
                raise VisionEvidenceContractError(
                    f"{path_str}.region_id: 送信していない領域{region_id!r}を参照しています"
                    f"（送信済みregion_id: {sorted(allowed_region_ids)}）"
                )


# ============================================================
# 1ページ分のパイロット実行（run_id単位・全attempt監査記録つき）
# ============================================================
def run_vision_evidence_pilot_page(
    client: "anthropic.Anthropic",
    *,
    run_id: str,
    pdf_page_no: int,
    expected_form_version: str,
    selected_business_date: date,
    output_dir: Path,
) -> dict:
    """1ページ分のVision抽出パイロットを実行し、run_id単位の監査記録(dict)を返す。

    - 画像はoutput_dir/{run_id}/images/へ保存する（base64本体は監査記録に含めない）。
    - 監査記録はoutput_dir/{run_id}/audit/p{page_no}_audit.json へ保存する。
    - 最終試行だけでなく、全attempt（成功・失敗いずれも）を"attempts"配列へ保存する。
      2回目で成功しても1回目の失敗記録は消さない。
    - 契約違反（VisionEvidenceContractError。region_id不正を含む）・JSON/tool_use破損
      （VisionApiCallError）・意味的不整合（EvidenceValidationError）・一時的APIエラーのみ、
      最大1回再試行する。読み取り結果が期待値と違うという理由での追加再試行はしない。
    - APIキー・画像base64本体は監査記録に一切含めない。
    - 失敗時に別の値を手作業で結果へ埋めることはしない（page_evidenceはNoneのまま）。
    """
    verify_source_pdf()
    pdf_page_index = pdf_page_to_index(pdf_page_no)

    run_dir = output_dir / run_id
    images_dir = run_dir / "images"
    images, image_manifest = build_crop_manifest(pdf_page_no, expected_form_version, images_dir=images_dir)
    region_ids_in_order = [img.label for img in images]
    allowed_region_ids = set(region_ids_in_order)
    include_store_code = "store_code_region" in allowed_region_ids

    prompt_text = build_region_scoped_prompt(
        page_no=pdf_page_no,
        form_version=expected_form_version,
        region_ids_in_order=region_ids_in_order,
    )

    audit: dict = {
        "run_id": run_id,
        "source_pdf_filename": SOURCE_PDF_FILENAME,
        "source_pdf_sha256": SOURCE_PDF_SHA256,
        "pdf_page_no": pdf_page_no,
        "pdf_page_index": pdf_page_index,
        "expected_form_version": expected_form_version,
        "selected_business_date": selected_business_date.isoformat(),
        "images": image_manifest,
        "contract_version": VISION_EVIDENCE_CONTRACT_VERSION,
        "prompt_version": VISION_EVIDENCE_PROMPT_VERSION,
        "model": VISION_MODEL,
        "max_tokens": VISION_MAX_TOKENS,
        "success": False,
        "attempt_count": 0,
        "page_evidence": None,
        "attempts": [],
    }

    def _finalize() -> dict:
        audit_dir = run_dir / "audit"
        audit_dir.mkdir(parents=True, exist_ok=True)
        audit_path = audit_dir / f"p{pdf_page_no:02d}_audit.json"
        audit_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
        return audit

    image_sha256_list = [img.sha256 for img in images]

    for attempt_number in range(1, MAX_RETRIES + 2):
        attempt_record: dict = {
            "attempt_number": attempt_number,
            "request_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "success": False,
            "error_type": None,
            "error_message": None,
            "raw_response_text": None,
            "parsed_payload": None,
            "input_tokens": None,
            "output_tokens": None,
            "stop_reason": None,
            "model": VISION_MODEL,
            "prompt_version": VISION_EVIDENCE_PROMPT_VERSION,
            "contract_version": VISION_EVIDENCE_CONTRACT_VERSION,
            "image_sha256_list": image_sha256_list,
        }
        audit["attempt_count"] = attempt_number

        try:
            message = _call_vision_api_once(
                client, images, prompt_text, include_store_code=include_store_code
            )
        except _TRANSIENT_API_ERRORS as exc:
            attempt_record["error_type"] = type(exc).__name__
            attempt_record["error_message"] = str(exc)
            audit["attempts"].append(attempt_record)
            if attempt_number <= MAX_RETRIES:
                continue
            return _finalize()
        except anthropic.AnthropicError as exc:
            # 認証エラー・不正リクエスト等、再試行しても解決しない異常は即座に失敗として記録する。
            attempt_record["error_type"] = f"non_retryable/{type(exc).__name__}"
            attempt_record["error_message"] = str(exc)
            audit["attempts"].append(attempt_record)
            return _finalize()

        attempt_record["stop_reason"] = getattr(message, "stop_reason", None)
        usage = _usage_to_dict(message)
        if usage:
            attempt_record["input_tokens"] = usage.get("input_tokens")
            attempt_record["output_tokens"] = usage.get("output_tokens")

        try:
            payload = _extract_tool_input(message)
            # raw_response_text/parsed_payloadは監査の正本としてVisionが実際に返した
            # 値のみを記録する（下記の合成store_codeを混ぜる前の状態）。
            attempt_record["raw_response_text"] = json.dumps(payload, ensure_ascii=False)
            attempt_record["parsed_payload"] = payload

            _validate_region_attribution(payload, allowed_region_ids)

            parse_input = payload
            if not include_store_code:
                # 旧帳票にはstore_code_regionを送っていない（Visionに推測させない）ため、
                # 「この帳票版には店舗コード欄自体が存在しない」という既知の事実を
                # クライアント側で合成する。Visionの出力ではないためraw_response_text/
                # parsed_payloadには混ぜない。
                parse_input = dict(payload)
                parse_input["store_code"] = {
                    "raw_value": None,
                    "status": "not_applicable",
                    "confidence": None,
                    "notes": "旧帳票のため店舗コード欄が存在しない（画像未送信、Vision非経由の既知情報）",
                }

            page_evidence = parse_vision_evidence_response(
                parse_input,
                expected_page_no=pdf_page_no,
                expected_form_version=expected_form_version,
                selected_business_date=selected_business_date,
            )
        except (VisionApiCallError, VisionEvidenceContractError, EvidenceValidationError) as exc:
            attempt_record["error_type"] = type(exc).__name__
            attempt_record["error_message"] = str(exc)
            audit["attempts"].append(attempt_record)
            if attempt_number <= MAX_RETRIES:
                continue
            return _finalize()

        attempt_record["success"] = True
        audit["attempts"].append(attempt_record)
        audit["success"] = True
        audit["page_evidence"] = page_evidence.to_dict(include_legacy=True)
        return _finalize()

    return _finalize()  # 理論上到達しない
