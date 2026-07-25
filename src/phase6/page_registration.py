"""Phase 6: ページ自動位置合わせ・領域構造（Step 3B v3 / page registration）。

設計根拠: Step 3B v3実装指示（2026-07-25）。

このモジュールの責務は「スキャン時の紙送り・位置合わせのばらつきにより生じる
ページ画像の平行移動（縦横のずれ）を、印刷済みの罫線・固定ラベルに相当する
テンプレート画像との比較だけから検出し、あらかじめ定義した領域（region）の
座標をそのずれ分だけ補正する」ことに限定される。

v2（vision_evidence_client.py の PAGE_REGION_OVERRIDES）は、実測した縦方向の
ずれをページ番号ごとに手作業でハードコードして吸収していた。このモジュールは
その代わりに、ページ番号にも手書き値・CSV値・正解値にも一切依存しない、
画像そのものの内容（印刷済みテンプレート）だけを根拠とする位置合わせを提供する。

明示的なスコープ外（今回は実装しない）:
    - 回転・拡大縮小・射影補正（平行移動のみを検出する）。
    - Vision API呼び出し・PDF読み込み（呼び出し側の責務。本モジュールはPIL.Imageの
      ピクセルデータのみを扱う）。
    - 新しい外部パッケージの追加（既存依存であるPillowのみを使用する）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from PIL import Image

__all__ = [
    "PageRegistrationError",
    "RegistrationNotMatchedError",
    "RegionOutOfBoundsError",
    "InvalidRegionPairError",
    "RegistrationStatus",
    "AnchorTemplate",
    "RegistrationResult",
    "RegionDefinition",
    "ResolvedRegion",
    "CellRegionPair",
    "StoreCodeRegionPair",
    "extract_anchor_template",
    "register_page",
    "resolve_regions",
    "resolve_cell_region_pair",
]


class PageRegistrationError(Exception):
    """このモジュールが送出する例外の基底クラス。"""


class RegistrationNotMatchedError(PageRegistrationError):
    """RegistrationResult.status が MATCHED でない状態で領域解決を試みた場合に送出する。
    信頼できない位置合わせのままVisionへ画像を渡すことを防ぐための構造的なガード。"""


class RegionOutOfBoundsError(PageRegistrationError):
    """平行移動後の領域が画像の境界外へはみ出す場合に送出する。
    黙って切り詰めず、明示的に失敗させる（誤ったクロップをVisionへ渡さないため）。"""


class InvalidRegionPairError(PageRegistrationError):
    """CellRegionPair/StoreCodeRegionPairのcontext/detail領域IDが、期待される命名規則
    （{cell_id}__context / {cell_id}__detail）と一致しない場合に送出する。"""


class RegistrationStatus(str, Enum):
    MATCHED = "matched"
    LOW_CONFIDENCE = "low_confidence"
    FAILED = "failed"


# ============================================================
# テンプレート・結果の型
# ============================================================
@dataclass(frozen=True)
class AnchorTemplate:
    """印刷済みの罫線・固定ラベルに相当する、テンプレート座標系での基準パターン。

    reference_x/reference_yは「ずれが一切ない場合」にこのパターンが現れるべき
    左上座標（テンプレート/基準の座標系）。reference_pixelsは、その位置から
    width×height切り出したグレースケール画素値（0-255）を行優先(row-major)で
    平坦化したタプル。実際の位置合わせは、対象画像の中でこのパターンに最も近い
    位置を探索し、その位置とreference_x/reference_yとの差を平行移動量とする。
    """

    template_id: str
    reference_x: int
    reference_y: int
    width: int
    height: int
    reference_pixels: tuple

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise PageRegistrationError(
                f"AnchorTemplateのwidth/heightは正数である必要があります: "
                f"width={self.width}, height={self.height}"
            )
        expected_len = self.width * self.height
        if len(self.reference_pixels) != expected_len:
            raise PageRegistrationError(
                f"reference_pixelsの長さがwidth*height({expected_len})と一致しません: "
                f"{len(self.reference_pixels)}"
            )


@dataclass(frozen=True)
class RegistrationResult:
    template_id: str
    x_offset: int
    y_offset: int
    score: float
    status: RegistrationStatus
    basis: str

    def to_dict(self) -> dict:
        return {
            "template_id": self.template_id,
            "x_offset": self.x_offset,
            "y_offset": self.y_offset,
            "score": self.score,
            "status": self.status.value,
            "basis": self.basis,
        }


@dataclass(frozen=True)
class RegionDefinition:
    """テンプレート/基準座標系における領域定義（未補正）。"""

    region_id: str
    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise PageRegistrationError(
                f"RegionDefinition({self.region_id!r})のwidth/heightは正数である必要があります: "
                f"width={self.width}, height={self.height}"
            )


@dataclass(frozen=True)
class ResolvedRegion:
    """RegistrationResultのx_offset/y_offsetで平行移動補正済みの、対象画像上の実座標。"""

    region_id: str
    x: int
    y: int
    width: int
    height: int

    def to_dict(self) -> dict:
        return {
            "region_id": self.region_id,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


# ============================================================
# Step 3B v3 Part C: context/detail 領域構造
# 同じセルをwritten用・tally用の別々の証拠として二重送信しない構造。
# 1セル(cell_id)につき、周辺文脈を含む広めの切り出し(context)と、数字/正の字を
# 判読するための密な切り出し(detail)の2領域だけを持つ。
# ============================================================
@dataclass(frozen=True)
class CellRegionPair:
    cell_id: str
    cell_context_region: RegionDefinition
    cell_detail_region: RegionDefinition

    def __post_init__(self) -> None:
        expected_context_id = f"{self.cell_id}__context"
        expected_detail_id = f"{self.cell_id}__detail"
        if self.cell_context_region.region_id != expected_context_id:
            raise InvalidRegionPairError(
                f"cell_id={self.cell_id!r}のcell_context_region.region_idは"
                f"{expected_context_id!r}である必要があります: "
                f"{self.cell_context_region.region_id!r}"
            )
        if self.cell_detail_region.region_id != expected_detail_id:
            raise InvalidRegionPairError(
                f"cell_id={self.cell_id!r}のcell_detail_region.region_idは"
                f"{expected_detail_id!r}である必要があります: "
                f"{self.cell_detail_region.region_id!r}"
            )

    def as_region_definitions(self) -> tuple:
        return (self.cell_context_region, self.cell_detail_region)


@dataclass(frozen=True)
class StoreCodeRegionPair:
    store_code_context_region: RegionDefinition
    store_code_detail_region: RegionDefinition

    def __post_init__(self) -> None:
        if self.store_code_context_region.region_id != "store_code__context":
            raise InvalidRegionPairError(
                "store_code_context_region.region_idは'store_code__context'である"
                f"必要があります: {self.store_code_context_region.region_id!r}"
            )
        if self.store_code_detail_region.region_id != "store_code__detail":
            raise InvalidRegionPairError(
                "store_code_detail_region.region_idは'store_code__detail'である"
                f"必要があります: {self.store_code_detail_region.region_id!r}"
            )

    def as_region_definitions(self) -> tuple:
        return (self.store_code_context_region, self.store_code_detail_region)


# ============================================================
# 位置合わせ（平行移動のみ。回転・拡大縮小・射影補正は対象外）
# ============================================================
def extract_anchor_template(
    image: "Image.Image",
    *,
    template_id: str,
    x: int,
    y: int,
    width: int,
    height: int,
) -> AnchorTemplate:
    """基準画像(image)のうち、テンプレート座標系(x, y, width, height)に相当する部分を
    グレースケールで切り出し、AnchorTemplateとして保持する。

    テストでは、この関数で「ずれのない基準画像」からテンプレートを作り、
    その後X/Y方向へ平行移動させた合成画像に対してregister_page()を呼び出すことで、
    平行移動検出のみを確認する（回転・拡大縮小は対象外）。
    """
    grayscale = image.convert("L")
    cropped = grayscale.crop((x, y, x + width, y + height))
    pixels = tuple(cropped.getdata())
    return AnchorTemplate(
        template_id=template_id,
        reference_x=x,
        reference_y=y,
        width=width,
        height=height,
        reference_pixels=pixels,
    )


def _patch_pixels(image: "Image.Image", x: int, y: int, width: int, height: int) -> tuple:
    box = (x, y, x + width, y + height)
    cropped = image.crop(box)
    return tuple(cropped.getdata())


def _similarity_score(a: tuple, b: tuple) -> float:
    """0.0(完全不一致)〜1.0(完全一致)。正規化した平均絶対誤差から算出する。"""
    total_diff = sum(abs(pa - pb) for pa, pb in zip(a, b))
    mean_diff = total_diff / len(a)
    return 1.0 - (mean_diff / 255.0)


def register_page(
    anchor_template: AnchorTemplate,
    target_image: "Image.Image",
    *,
    search_range: int = 15,
    matched_score_threshold: float = 0.92,
    low_confidence_score_threshold: float = 0.75,
) -> RegistrationResult:
    """target_image内で anchor_template.reference_pixels に最も近いパターンの位置を
    探索し、reference_x/reference_yとの差を平行移動量(x_offset, y_offset)として返す。

    ページ番号・手書き値・CSV値・正解値は一切参照しない（画像内容のみを根拠とする）。
    回転・拡大縮小・射影補正は行わない（search_range内の平行移動のみを探索する）。
    """
    grayscale_target = target_image.convert("L")
    target_width, target_height = grayscale_target.size

    best_score = -1.0
    best_dx = 0
    best_dy = 0

    for dy in range(-search_range, search_range + 1):
        candidate_y = anchor_template.reference_y + dy
        if candidate_y < 0 or candidate_y + anchor_template.height > target_height:
            continue
        for dx in range(-search_range, search_range + 1):
            candidate_x = anchor_template.reference_x + dx
            if candidate_x < 0 or candidate_x + anchor_template.width > target_width:
                continue
            candidate_pixels = _patch_pixels(
                grayscale_target, candidate_x, candidate_y, anchor_template.width, anchor_template.height
            )
            score = _similarity_score(anchor_template.reference_pixels, candidate_pixels)
            if score > best_score:
                best_score = score
                best_dx = dx
                best_dy = dy

    if best_score < 0:
        # 探索範囲内に候補が1件もなかった（画像が小さすぎる等）。
        return RegistrationResult(
            template_id=anchor_template.template_id,
            x_offset=0,
            y_offset=0,
            score=0.0,
            status=RegistrationStatus.FAILED,
            basis=(
                f"search_range={search_range}内に有効な候補領域が1件もありませんでした"
                f"（対象画像サイズ: {target_width}x{target_height}）"
            ),
        )

    if best_score >= matched_score_threshold:
        status = RegistrationStatus.MATCHED
    elif best_score >= low_confidence_score_threshold:
        status = RegistrationStatus.LOW_CONFIDENCE
    else:
        status = RegistrationStatus.FAILED

    return RegistrationResult(
        template_id=anchor_template.template_id,
        x_offset=best_dx,
        y_offset=best_dy,
        score=best_score,
        status=status,
        basis=(
            f"anchor template一致探索（search_range={search_range}, "
            f"matched_threshold={matched_score_threshold}, "
            f"low_confidence_threshold={low_confidence_score_threshold}, "
            f"best_score={best_score:.4f}）"
        ),
    )


def resolve_regions(
    region_definitions: list,
    registration: RegistrationResult,
    *,
    image_width: int,
    image_height: int,
) -> list:
    """RegionDefinitionのリストへ、位置合わせで検出した平行移動量を適用し、
    対象画像上の実座標(ResolvedRegion)へ変換する。

    registration.statusがMATCHEDでない場合は解決を拒否する（失敗時にVisionを
    呼ばない設計を、呼び出し側の判断ミスに関わらず構造的に強制するため）。
    平行移動後に画像境界の外へ出る領域がある場合も、黙って切り詰めずに拒否する。
    """
    if registration.status != RegistrationStatus.MATCHED:
        raise RegistrationNotMatchedError(
            f"registration.status={registration.status.value!r}のため領域を解決できません"
            "（matchedの場合のみ解決可能。低信頼・失敗時はVisionを呼ばない設計）"
        )

    resolved = []
    for region in region_definitions:
        x = region.x + registration.x_offset
        y = region.y + registration.y_offset
        if x < 0 or y < 0 or x + region.width > image_width or y + region.height > image_height:
            raise RegionOutOfBoundsError(
                f"region_id={region.region_id!r}: 平行移動後の領域"
                f"(x={x}, y={y}, width={region.width}, height={region.height})"
                f"が画像境界(width={image_width}, height={image_height})の外にはみ出します"
            )
        resolved.append(
            ResolvedRegion(region_id=region.region_id, x=x, y=y, width=region.width, height=region.height)
        )
    return resolved


def resolve_cell_region_pair(
    pair,
    registration: RegistrationResult,
    *,
    image_width: int,
    image_height: int,
) -> tuple:
    """CellRegionPair/StoreCodeRegionPairのcontext/detail領域をまとめて解決する。
    戻り値は(context: ResolvedRegion, detail: ResolvedRegion)。"""
    context_def, detail_def = pair.as_region_definitions()
    resolved = resolve_regions(
        [context_def, detail_def],
        registration,
        image_width=image_width,
        image_height=image_height,
    )
    return resolved[0], resolved[1]
