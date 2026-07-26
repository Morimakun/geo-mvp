"""Step 3B v3: ページ自動位置合わせ・領域構造(page_registration.py)のテスト。

このテストは合成画像のみを使用する（実PDF・実Excel・Vision APIには一切アクセスしない）。
すべての画像はPillowでテスト内で生成する架空のパターンであり、実際の帳票画像ではない。
"""

from __future__ import annotations

import io
import random
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.phase6.page_registration import (  # noqa: E402
    AnchorTemplate,
    CellRegionPair,
    InvalidRegionPairError,
    RegionDefinition,
    RegionOutOfBoundsError,
    RegistrationNotMatchedError,
    RegistrationStatus,
    StoreCodeRegionPair,
    extract_anchor_template,
    register_page,
    resolve_cell_region_pair,
    resolve_regions,
)

CANVAS_SIZE = (200, 200)
MARKER_SIZE = 20
MARKER_X = 80
MARKER_Y = 80


def _blank_canvas(fill: int = 255) -> Image.Image:
    return Image.new("L", CANVAS_SIZE, color=fill)


def _canvas_with_marker(*, x: int, y: int, fill: int = 0, size: int = MARKER_SIZE) -> Image.Image:
    img = _blank_canvas()
    draw = ImageDraw.Draw(img)
    draw.rectangle([x, y, x + size - 1, y + size - 1], fill=fill)
    return img


def _reference_template() -> AnchorTemplate:
    reference_image = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)
    return extract_anchor_template(
        reference_image, template_id="synthetic_anchor", x=MARKER_X, y=MARKER_Y, width=MARKER_SIZE, height=MARKER_SIZE
    )


# ============================================================
# 平行移動検出（回転・拡大縮小は対象外）
# ============================================================
class TestTranslationDetection:
    def test_x_direction_shift_is_detected(self):
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X + 7, y=MARKER_Y)

        result = register_page(template, shifted)

        assert result.status == RegistrationStatus.MATCHED
        assert result.x_offset == 7
        assert result.y_offset == 0
        assert result.score > 0.99

    def test_x_direction_negative_shift_is_detected(self):
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X - 5, y=MARKER_Y)

        result = register_page(template, shifted)

        assert result.status == RegistrationStatus.MATCHED
        assert result.x_offset == -5
        assert result.y_offset == 0

    def test_y_direction_shift_is_detected(self):
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X, y=MARKER_Y + 9)

        result = register_page(template, shifted)

        assert result.status == RegistrationStatus.MATCHED
        assert result.x_offset == 0
        assert result.y_offset == 9
        assert result.score > 0.99

    def test_combined_x_and_y_shift_is_detected(self):
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X + 4, y=MARKER_Y - 6)

        result = register_page(template, shifted)

        assert result.status == RegistrationStatus.MATCHED
        assert result.x_offset == 4
        assert result.y_offset == -6

    def test_unshifted_image_gives_zero_offset(self):
        template = _reference_template()
        unshifted = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)

        result = register_page(template, unshifted)

        assert result.x_offset == 0
        assert result.y_offset == 0
        assert result.status == RegistrationStatus.MATCHED

    def test_offset_is_independent_of_which_logical_page_the_image_represents(self):
        """register_pageはpage_noを一切引数に取らない。異なる「ページ」由来だと
        呼び出し側が認識していても、画像内容が同一であれば同一の結果になることを確認する
        （ページ番号からオフセットを決めていないことの裏付け）。"""
        template = _reference_template()
        page_5_image = _canvas_with_marker(x=MARKER_X + 3, y=MARKER_Y + 2)
        page_12_image = _canvas_with_marker(x=MARKER_X + 3, y=MARKER_Y + 2)

        result_for_page_5 = register_page(template, page_5_image)
        result_for_page_12 = register_page(template, page_12_image)

        assert result_for_page_5.x_offset == result_for_page_12.x_offset == 3
        assert result_for_page_5.y_offset == result_for_page_12.y_offset == 2
        assert result_for_page_5.score == result_for_page_12.score
        assert result_for_page_5.status == result_for_page_12.status == RegistrationStatus.MATCHED


# ============================================================
# 信頼度低下・失敗
# ============================================================
class TestConfidenceThresholds:
    def test_marker_absent_gives_failed_status(self):
        template = _reference_template()
        blank = _blank_canvas()

        result = register_page(template, blank)

        assert result.status == RegistrationStatus.FAILED
        assert result.score < 0.75

    def test_degraded_marker_gives_low_confidence_status(self):
        template = _reference_template()
        # 完全一致(黒=0)でも完全不一致(白=255)でもない中間濃度のマーカー。
        degraded = _canvas_with_marker(x=MARKER_X, y=MARKER_Y, fill=40)

        result = register_page(template, degraded)

        assert result.status == RegistrationStatus.LOW_CONFIDENCE
        assert 0.75 <= result.score < 0.92


# ============================================================
# 失敗時はVisionを呼ばない設計（resolve_regionsが構造的に強制する）
# ============================================================
class TestFailedRegistrationBlocksRegionResolution:
    def test_low_confidence_registration_cannot_resolve_regions(self):
        template = _reference_template()
        degraded = _canvas_with_marker(x=MARKER_X, y=MARKER_Y, fill=40)
        registration = register_page(template, degraded)
        assert registration.status == RegistrationStatus.LOW_CONFIDENCE

        with pytest.raises(RegistrationNotMatchedError):
            resolve_regions(
                [RegionDefinition("some_region", 10, 10, 20, 20)],
                registration,
                image_width=CANVAS_SIZE[0],
                image_height=CANVAS_SIZE[1],
            )

    def test_failed_registration_cannot_resolve_regions(self):
        template = _reference_template()
        blank = _blank_canvas()
        registration = register_page(template, blank)
        assert registration.status == RegistrationStatus.FAILED

        with pytest.raises(RegistrationNotMatchedError):
            resolve_regions(
                [RegionDefinition("some_region", 10, 10, 20, 20)],
                registration,
                image_width=CANVAS_SIZE[0],
                image_height=CANVAS_SIZE[1],
            )


# ============================================================
# 領域の平行移動補正・境界チェック
# ============================================================
class TestResolveRegions:
    def test_matched_registration_translates_region_coordinates(self):
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X + 5, y=MARKER_Y + 3)
        registration = register_page(template, shifted)
        assert registration.status == RegistrationStatus.MATCHED

        region = RegionDefinition("intro__detail", x=50, y=50, width=20, height=20)
        resolved = resolve_regions(
            [region], registration, image_width=CANVAS_SIZE[0], image_height=CANVAS_SIZE[1]
        )

        assert resolved[0].region_id == "intro__detail"
        assert resolved[0].x == 55
        assert resolved[0].y == 53

    def test_region_translated_outside_image_bounds_raises(self):
        template = _reference_template()
        # 探索範囲(デフォルトsearch_range=15)内で、右下方向へ大きくずらす。
        shifted = _canvas_with_marker(x=MARKER_X + 15, y=MARKER_Y + 15)
        registration = register_page(template, shifted)
        assert registration.status == RegistrationStatus.MATCHED
        assert registration.x_offset == 15
        assert registration.y_offset == 15

        # 画像端ぎりぎりの領域が、平行移動後に境界外へはみ出すように設計する。
        region = RegionDefinition(
            "near_edge", x=CANVAS_SIZE[0] - 20, y=10, width=15, height=15
        )
        with pytest.raises(RegionOutOfBoundsError):
            resolve_regions(
                [region], registration, image_width=CANVAS_SIZE[0], image_height=CANVAS_SIZE[1]
            )


# ============================================================
# Part C: context/detail 領域構造（同一cell_idへの紐づけ）
# ============================================================
class TestCellRegionPair:
    def test_valid_pair_binds_context_and_detail_to_same_cell_id(self):
        pair = CellRegionPair(
            cell_id="intro",
            cell_context_region=RegionDefinition("intro__context", 100, 100, 60, 40),
            cell_detail_region=RegionDefinition("intro__detail", 110, 110, 20, 15),
        )
        assert pair.cell_context_region.region_id == "intro__context"
        assert pair.cell_detail_region.region_id == "intro__detail"

    def test_mismatched_context_region_id_is_rejected(self):
        with pytest.raises(InvalidRegionPairError):
            CellRegionPair(
                cell_id="intro",
                cell_context_region=RegionDefinition("voice__context", 100, 100, 60, 40),
                cell_detail_region=RegionDefinition("intro__detail", 110, 110, 20, 15),
            )

    def test_mismatched_detail_region_id_is_rejected(self):
        with pytest.raises(InvalidRegionPairError):
            CellRegionPair(
                cell_id="intro",
                cell_context_region=RegionDefinition("intro__context", 100, 100, 60, 40),
                cell_detail_region=RegionDefinition("voice__detail", 110, 110, 20, 15),
            )

    def test_resolve_cell_region_pair_applies_same_offset_to_both_regions(self):
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X + 2, y=MARKER_Y + 1)
        registration = register_page(template, shifted)

        pair = CellRegionPair(
            cell_id="intro",
            cell_context_region=RegionDefinition("intro__context", 20, 20, 60, 40),
            cell_detail_region=RegionDefinition("intro__detail", 30, 30, 20, 15),
        )
        context, detail = resolve_cell_region_pair(
            pair, registration, image_width=CANVAS_SIZE[0], image_height=CANVAS_SIZE[1]
        )

        assert context.region_id == "intro__context"
        assert context.x == 22 and context.y == 21
        assert detail.region_id == "intro__detail"
        assert detail.x == 32 and detail.y == 31


class TestStoreCodeRegionPair:
    def test_valid_pair_is_accepted(self):
        pair = StoreCodeRegionPair(
            store_code_context_region=RegionDefinition("store_code__context", 5, 5, 100, 20),
            store_code_detail_region=RegionDefinition("store_code__detail", 10, 8, 80, 14),
        )
        assert pair.store_code_context_region.region_id == "store_code__context"

    def test_wrong_region_id_naming_is_rejected(self):
        with pytest.raises(InvalidRegionPairError):
            StoreCodeRegionPair(
                store_code_context_region=RegionDefinition("wrong_name", 5, 5, 100, 20),
                store_code_detail_region=RegionDefinition("store_code__detail", 10, 8, 80, 14),
            )


# ============================================================
# 合成ストレステスト（実帳票・実座標・ページ番号・CSV値・正解値は一切使わない）
#
# ここでの各テストは、現行の単純な画素比較アルゴリズム（回転・拡大縮小・照明正規化
# なしの総当たりテンプレートマッチ）が「保証する仕様」（探索範囲内の平行移動の
# 検出、境界チェック等）と、「既知の限界」（大きな輝度変化・大きな欠損等では
# matchedにならない）を区別して記録する。既知の限界側のテストで閾値やアルゴリズムを
# 実データに合わせて調整することはしない。
# ============================================================
def _jpeg_round_trip(image: Image.Image, *, quality: int = 90) -> Image.Image:
    buf = io.BytesIO()
    image.convert("L").save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("L").copy()


def _add_seeded_noise(image: Image.Image, *, seed: int, amplitude: int) -> Image.Image:
    rng = random.Random(seed)
    noisy = image.copy()
    pixels = noisy.load()
    width, height = noisy.size
    for y in range(height):
        for x in range(width):
            delta = rng.randint(-amplitude, amplitude)
            pixels[x, y] = max(0, min(255, pixels[x, y] + delta))
    return noisy


class TestSearchRangeBoundary:
    def test_shift_exactly_at_search_range_boundary_is_matched(self):
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X + 15, y=MARKER_Y)  # 既定search_range=15の境界

        result = register_page(template, shifted, search_range=15)

        assert result.status == RegistrationStatus.MATCHED
        assert result.x_offset == 15

    def test_shift_far_beyond_search_range_with_zero_possible_overlap_is_not_matched(self):
        # search_range=15かつマーカー幅20の場合、真の移動量が35以上あれば、
        # 探索範囲内のどの候補ウィンドウとも重なりが一切生じない
        # （保証される仕様：この場合は確実にmatchedにならない）。
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X + 40, y=MARKER_Y)

        result = register_page(template, shifted, search_range=15)

        assert result.status == RegistrationStatus.FAILED
        assert result.score == 0.0

    def test_shift_just_beyond_search_range_can_still_score_high_known_limitation(self):
        # 既知の限界: 現行アルゴリズムは単純な画素平均絶対誤差による総当たりマッチであり、
        # 回転・拡大縮小・照明正規化を行わない。今回のテスト用マーカーのような
        # 大きな単色パターンでは、真の移動量が探索範囲のわずか1px外側（ここでは16px、
        # search_range=15）であっても、境界の候補ウィンドウ（オフセット15px）が
        # マーカーの大部分（20列中19列相当）と重なるため、高いスコアで誤って
        # matchedと判定されうる（かつ報告されるオフセットは真の値と1pxずれる）。
        # このテストはこの限界を意図的に固定するものであり、閾値やアルゴリズムを
        # 調整して「探索範囲外は必ずmatchedにしない」という仕様を無理に満たさせない。
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X + 16, y=MARKER_Y)

        result = register_page(template, shifted, search_range=15)

        assert result.status == RegistrationStatus.MATCHED  # 既知の限界（保証仕様ではない）
        assert result.x_offset == 15  # 真の移動量16とは1pxずれる


class TestMildImageDegradation:
    """既知の限界: 大きな輝度変化・大きな欠損はmatchedを保証しない（意図的に緩めない）。"""

    def test_slight_brightness_change_still_matches(self):
        template = _reference_template()
        # 純黒(0)ではなく、わずかに明るいマーカー（軽度の輝度変化を模す）。
        slightly_brighter = _canvas_with_marker(x=MARKER_X + 4, y=MARKER_Y, fill=10)

        result = register_page(template, slightly_brighter)

        assert result.status == RegistrationStatus.MATCHED
        assert result.x_offset == 4

    def test_fixed_seed_slight_noise_still_matches(self):
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X + 5, y=MARKER_Y - 3)
        noisy = _add_seeded_noise(shifted, seed=12345, amplitude=6)

        result = register_page(template, noisy)

        assert result.status == RegistrationStatus.MATCHED
        assert result.x_offset == 5
        assert result.y_offset == -3

    def test_jpeg_recompression_equivalent_degradation_still_matches(self):
        template = _reference_template()
        shifted = _canvas_with_marker(x=MARKER_X + 2, y=MARKER_Y + 2)
        recompressed = _jpeg_round_trip(shifted, quality=90)

        result = register_page(template, recompressed)

        assert result.status == RegistrationStatus.MATCHED
        assert result.x_offset == 2
        assert result.y_offset == 2

    def test_small_anchor_notch_occlusion_degrades_to_low_confidence(self):
        # アンカー一部欠損（軽度）: マーカー内の小さな角を白抜きにする。
        template = _reference_template()
        shifted_x, shifted_y = MARKER_X, MARKER_Y
        img = _canvas_with_marker(x=shifted_x, y=shifted_y)
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [shifted_x, shifted_y, shifted_x + 4, shifted_y + 9],  # 20x20のうち5x10=50画素を欠損
            fill=255,
        )

        result = register_page(template, img)

        assert result.status != RegistrationStatus.MATCHED
        assert result.score < 0.92

    def test_half_anchor_occlusion_fails(self):
        # アンカー一部欠損（重度）: マーカーの半分を白抜きにする。
        template = _reference_template()
        img = _canvas_with_marker(x=MARKER_X, y=MARKER_Y)
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [MARKER_X, MARKER_Y, MARKER_X + MARKER_SIZE - 1, MARKER_Y + MARKER_SIZE // 2 - 1],
            fill=255,
        )

        result = register_page(template, img)

        assert result.status == RegistrationStatus.FAILED


class TestAmbiguousAndDegenerateInputs:
    def test_multiple_identical_candidates_still_returns_deterministically(self):
        # 探索範囲内に完全一致するマーカーが2箇所ある場合でも、例外を出さず
        # 決定論的に（毎回同じ）候補を1つ選ぶことだけを確認する
        # （どちらが「正しい」かはこのテストの対象外）。
        template = _reference_template()
        img = _blank_canvas()
        draw = ImageDraw.Draw(img)
        draw.rectangle(
            [MARKER_X + 3, MARKER_Y, MARKER_X + 3 + MARKER_SIZE - 1, MARKER_Y + MARKER_SIZE - 1], fill=0
        )
        draw.rectangle(
            [MARKER_X + 8, MARKER_Y, MARKER_X + 8 + MARKER_SIZE - 1, MARKER_Y + MARKER_SIZE - 1], fill=0
        )

        result_1 = register_page(template, img)
        result_2 = register_page(template, img)

        assert result_1.status == RegistrationStatus.MATCHED
        assert result_1.x_offset in (3, 8)
        assert result_1.x_offset == result_2.x_offset  # 決定論的（毎回同じ結果）
        assert result_1.score == result_2.score

    def test_target_image_smaller_than_anchor_fails_without_crashing(self):
        template = _reference_template()  # 20x20のアンカー
        tiny_target = Image.new("L", (15, 15), color=255)  # アンカーより小さい画像

        result = register_page(template, tiny_target)

        assert result.status == RegistrationStatus.FAILED
        assert result.score == 0.0
