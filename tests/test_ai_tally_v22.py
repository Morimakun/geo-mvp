"""
Unit Tests for AI Tally V2.2 Classification Module

Test Strategy:
- auto_confirm_candidate and review_required are mutually exclusive
- Each should be in exactly one category
- Both conditions should be enforced strictly
"""

import sys
from pathlib import Path

# Import module from scripts
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from ai_tally_v22 import (
    classify_ai_tally_result,
    normalize_ai_tally_value,
    compare_ai_tally_with_csv,
    build_ai_tally_review_flags,
    AITallyClassification
)


class TestNormalizeValue:
    """Test value normalization function."""

    def test_normalize_blank_string_to_zero(self):
        """'blank' string should be normalized to 0."""
        assert normalize_ai_tally_value("blank") == 0

    def test_normalize_empty_string_to_none(self):
        """Empty string should be None."""
        assert normalize_ai_tally_value("") is None

    def test_normalize_none_to_none(self):
        """None should remain None."""
        assert normalize_ai_tally_value(None) is None

    def test_normalize_string_number(self):
        """String number should be converted to int."""
        assert normalize_ai_tally_value("2") == 2
        assert normalize_ai_tally_value("5") == 5

    def test_normalize_float_to_int(self):
        """Float should be converted to int."""
        assert normalize_ai_tally_value(2.0) == 2
        assert normalize_ai_tally_value(5.7) == 5

    def test_normalize_int_unchanged(self):
        """Int should remain unchanged."""
        assert normalize_ai_tally_value(2) == 2


class TestCompareWithCSV:
    """Test CSV comparison function."""

    def test_exact_match(self):
        """v22 == csv should set csv_match to True."""
        result = compare_ai_tally_with_csv(5, 5, 5)
        assert result["csv_match"] is True
        assert result["v22_vs_csv_diff"] == 0

    def test_mismatch(self):
        """v22 != csv should set csv_match to False."""
        result = compare_ai_tally_with_csv(2, 11, 9)
        assert result["csv_match"] is False
        assert result["v22_vs_csv_diff"] == 9

    def test_v22_closer_than_v3(self):
        """v22 closer to CSV than v3 should be detected."""
        # v22=2, v3=9, csv=3
        # |2-3|=1 < |9-3|=6
        result = compare_ai_tally_with_csv(2, 3, 9)
        assert result["v22_closer_than_v3"] is True
        assert result["v22_vs_csv_diff"] == 1
        assert result["v22_vs_v3_diff"] == 7

    def test_v22_worse_than_v3_p16_rule(self):
        """P16 rule: v22 worse than v3 (farther from CSV)."""
        # v22=2, v3=9, csv=11
        # |2-11|=9 > |9-11|=2 (degradation)
        result = compare_ai_tally_with_csv(2, 11, 9)
        assert result["v22_worse_than_v3"] is True

    def test_none_values(self):
        """None values should not crash comparison."""
        result = compare_ai_tally_with_csv(None, 5, None)
        assert result["v22_vs_csv_diff"] == 0
        assert result["csv_match"] is False


class TestBuildReviewFlags:
    """Test review_required flag builder."""

    def test_target_cell_not_found(self):
        """target_cell_found=False should trigger review."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=False,
            estimated_value=5,
            confidence="medium",
            v22_value=5,
            csv_value=5,
            v3_value=5,
            visible_mark_type="tally"
        )
        assert review_required is True
        assert any("target_cell_found" in r for r in reasons)

    def test_estimated_value_null(self):
        """estimated_value=None should trigger review."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=True,
            estimated_value=None,
            confidence="medium",
            v22_value=None,
            csv_value=5,
            v3_value=5,
            visible_mark_type="tally"
        )
        assert review_required is True
        assert any("estimated_value" in r for r in reasons)

    def test_confidence_low(self):
        """confidence=low should trigger review."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=True,
            estimated_value=5,
            confidence="low",
            v22_value=5,
            csv_value=5,
            v3_value=5,
            visible_mark_type="tally"
        )
        assert review_required is True
        assert any("confidence" in r for r in reasons)

    def test_csv_mismatch(self):
        """v22 != csv should trigger review."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=True,
            estimated_value=2,
            confidence="medium",
            v22_value=2,
            csv_value=11,
            v3_value=9,
            visible_mark_type="tally"
        )
        assert review_required is True
        assert any("CSV" in r or "csv" in r for r in reasons)

    def test_blank_with_csv_value(self):
        """blank mark_type + csv_value > 0 should trigger review."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=True,
            estimated_value=0,
            confidence="medium",
            v22_value=0,
            csv_value=2,
            v3_value=0,
            visible_mark_type="blank"
        )
        assert review_required is True
        assert any("blank" in r for r in reasons)

    def test_large_diff_with_v3_but_csv_match(self):
        """|v22 - v3| >= 3 should NOT trigger review if v22==csv (OCR correction case)."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=True,
            estimated_value=3,
            confidence="medium",
            v22_value=3,
            csv_value=3,
            v3_value=34,  # Large error in v3, but v22 corrects it
            visible_mark_type="tally"
        )
        assert review_required is False
        assert len(reasons) == 0

    def test_large_diff_with_v3_no_csv_match(self):
        """|v22 - v3| >= 3 AND v22!=csv should trigger review."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=True,
            estimated_value=2,
            confidence="medium",
            v22_value=2,
            csv_value=11,
            v3_value=9,  # Large diff: |2-9|=7 >= 3
            visible_mark_type="tally"
        )
        assert review_required is True
        assert any("大差" in r for r in reasons)

    def test_p16_degradation_rule(self):
        """P16 rule: v22 farther from CSV than v3."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=True,
            estimated_value=2,
            confidence="medium",
            v22_value=2,
            csv_value=11,
            v3_value=9,
            visible_mark_type="tally"
        )
        # |2-11|=9 > |9-11|=2 → degradation detected
        assert review_required is True
        assert any("悪化検知" in r for r in reasons)

    def test_unclear_mark_type(self):
        """visible_mark_type=unclear should trigger review."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=True,
            estimated_value=5,
            confidence="medium",
            v22_value=5,
            csv_value=5,
            v3_value=5,
            visible_mark_type="unclear"
        )
        assert review_required is True
        assert any("unclear" in r for r in reasons)

    def test_unknown_mark_type(self):
        """visible_mark_type=unknown should trigger review."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=True,
            estimated_value=5,
            confidence="medium",
            v22_value=5,
            csv_value=5,
            v3_value=5,
            visible_mark_type="unknown"
        )
        assert review_required is True
        assert any("unknown" in r for r in reasons)

    def test_no_review_needed(self):
        """Perfect case should not trigger review."""
        review_required, reasons = build_ai_tally_review_flags(
            target_cell_found=True,
            estimated_value=5,
            confidence="medium",
            v22_value=5,
            csv_value=5,
            v3_value=5,
            visible_mark_type="tally"
        )
        assert review_required is False
        assert len(reasons) == 0


class TestClassifyAutoConfirm:
    """Test auto_confirm_candidate classification."""

    def test_csv_match_medium_confidence(self):
        """CSV一致・medium confidence → auto_confirm true."""
        result = classify_ai_tally_result(
            v22_estimated_value=5,
            csv_ai_value=5,
            v3_ai_value=5,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P1"
        )
        assert result.auto_confirm_candidate is True
        assert result.review_required is False
        assert result.classification == AITallyClassification.AUTO_CONFIRM

    def test_csv_match_high_confidence(self):
        """CSV一致・high confidence → auto_confirm true."""
        result = classify_ai_tally_result(
            v22_estimated_value=3,
            csv_ai_value=3,
            v3_ai_value=3,
            confidence="high",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P3"
        )
        assert result.auto_confirm_candidate is True

    def test_blank_csv_zero(self):
        """blank mark_type + csv=0 → auto_confirm candidate."""
        result = classify_ai_tally_result(
            v22_estimated_value=0,
            csv_ai_value=0,
            v3_ai_value=0,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="blank",
            page_id="P2"
        )
        assert result.auto_confirm_candidate is True
        assert result.review_required is False

    def test_digit_mark_type(self):
        """digit mark_type with CSV match → auto_confirm."""
        result = classify_ai_tally_result(
            v22_estimated_value=2,
            csv_ai_value=2,
            v3_ai_value=2,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="digit",
            page_id="P5"
        )
        assert result.auto_confirm_candidate is True


class TestClassifyReviewRequired:
    """Test review_required classification."""

    def test_csv_mismatch(self):
        """CSV不一致 → review_required true."""
        result = classify_ai_tally_result(
            v22_estimated_value=2,
            csv_ai_value=11,
            v3_ai_value=9,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P16"
        )
        assert result.auto_confirm_candidate is False
        assert result.review_required is True
        assert result.classification == AITallyClassification.REVIEW_REQUIRED

    def test_confidence_low(self):
        """confidence=low → review_required true, low_confidence class."""
        result = classify_ai_tally_result(
            v22_estimated_value=2,
            csv_ai_value=2,
            v3_ai_value=4,
            confidence="low",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P15"
        )
        assert result.auto_confirm_candidate is False
        assert result.review_required is True
        assert result.classification == AITallyClassification.LOW_CONFIDENCE

    def test_target_cell_not_found(self):
        """target_cell_found=False → review_required true."""
        result = classify_ai_tally_result(
            v22_estimated_value=None,
            csv_ai_value=5,
            v3_ai_value=5,
            confidence="medium",
            target_cell_found=False,
            visible_mark_type="unknown",
            page_id="P99"
        )
        assert result.auto_confirm_candidate is False
        assert result.review_required is True

    def test_blank_csv_nonzero(self):
        """blank判定でCSV > 0 → review_required true."""
        result = classify_ai_tally_result(
            v22_estimated_value=0,
            csv_ai_value=2,
            v3_ai_value=0,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="blank",
            page_id="P11"
        )
        assert result.auto_confirm_candidate is False
        assert result.review_required is True

    def test_p16_degradation(self):
        """P16型悪化ケース → review_required true."""
        result = classify_ai_tally_result(
            v22_estimated_value=2,
            csv_ai_value=11,
            v3_ai_value=9,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P16"
        )
        # |2-11|=9 > |9-11|=2 →悪化
        assert result.auto_confirm_candidate is False
        assert result.review_required is True
        assert result.v22_worse_than_v3 is True

    def test_v3_large_error_corrected(self):
        """v3大誤読・v22=CSV → OCR補正候補（auto_confirmも true）."""
        result = classify_ai_tally_result(
            v22_estimated_value=3,
            csv_ai_value=3,
            v3_ai_value=34,  # v3 wrongly read 34
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P14"
        )
        # v22==csv && |v22-v3|>=3 → OCR補正として認識
        assert result.auto_confirm_candidate is True
        assert result.review_required is False
        assert result.classification == AITallyClassification.OCR_CORRECTION


class TestMutualExclusion:
    """Test that auto_confirm and review_required are mutually exclusive."""

    def test_perfect_case_no_review(self):
        """Perfect match should be auto_confirm ONLY."""
        result = classify_ai_tally_result(
            v22_estimated_value=5,
            csv_ai_value=5,
            v3_ai_value=5,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P1"
        )
        assert result.auto_confirm_candidate is True
        assert result.review_required is False

    def test_mismatch_no_auto_confirm(self):
        """Mismatch should be review ONLY."""
        result = classify_ai_tally_result(
            v22_estimated_value=2,
            csv_ai_value=5,
            v3_ai_value=5,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P2"
        )
        assert result.auto_confirm_candidate is False
        assert result.review_required is True

    def test_low_confidence_no_auto_confirm(self):
        """Low confidence should be review ONLY."""
        result = classify_ai_tally_result(
            v22_estimated_value=5,
            csv_ai_value=5,
            v3_ai_value=5,
            confidence="low",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P15"
        )
        assert result.auto_confirm_candidate is False
        assert result.review_required is True

    def test_target_not_found_no_auto_confirm(self):
        """target_cell_found=False should be review ONLY."""
        result = classify_ai_tally_result(
            v22_estimated_value=None,
            csv_ai_value=5,
            v3_ai_value=5,
            confidence="medium",
            target_cell_found=False,
            visible_mark_type="unknown",
            page_id="P99"
        )
        assert result.auto_confirm_candidate is False
        assert result.review_required is True

    def test_no_never_both_true(self):
        """auto_confirm and review_required should never both be true."""
        test_cases = [
            # (v22, csv, v3, conf, target, mark_type)
            (5, 5, 5, "medium", True, "tally"),      # auto
            (2, 5, 5, "medium", True, "tally"),      # review
            (5, 5, 5, "low", True, "tally"),         # review
            (0, 0, 0, "medium", True, "blank"),      # auto
            (0, 2, 0, "medium", True, "blank"),      # review
            (3, 3, 34, "medium", True, "tally"),     # ocr_correction (auto)
            (2, 11, 9, "medium", True, "tally"),     # p16 (review)
        ]

        for v22, csv, v3, conf, target, mark in test_cases:
            result = classify_ai_tally_result(
                v22_estimated_value=v22,
                csv_ai_value=csv,
                v3_ai_value=v3,
                confidence=conf,
                target_cell_found=target,
                visible_mark_type=mark,
                page_id="TEST"
            )
            # Exactly one should be true
            xor_result = result.auto_confirm_candidate != result.review_required
            assert xor_result, (
                f"Case ({v22}, {csv}, {v3}, {conf}): "
                f"auto={result.auto_confirm_candidate}, "
                f"review={result.review_required} - NOT XOR!"
            )


class TestDisplayMessages:
    """Test display message generation."""

    def test_auto_confirm_message(self):
        """Auto confirm should have skip-friendly message."""
        result = classify_ai_tally_result(
            v22_estimated_value=5,
            csv_ai_value=5,
            v3_ai_value=5,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P1"
        )
        assert "自動確定候補" in result.display_message
        assert "スキップ" in result.display_message
        assert result.action_recommended == "skip"

    def test_review_required_message(self):
        """Review required should have confirm-friendly message."""
        result = classify_ai_tally_result(
            v22_estimated_value=2,
            csv_ai_value=11,
            v3_ai_value=9,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P16"
        )
        assert "要確認" in result.display_message
        assert result.action_recommended == "confirm"

    def test_low_confidence_message(self):
        """Low confidence should mention forced review."""
        result = classify_ai_tally_result(
            v22_estimated_value=2,
            csv_ai_value=2,
            v3_ai_value=4,
            confidence="low",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P15"
        )
        assert "低信頼度" in result.display_message
        assert "強制確認" in result.display_message or "必ず確認" in result.display_message
        assert result.action_recommended == "force_review"

    def test_ocr_correction_message(self):
        """OCR correction should mention improvement."""
        result = classify_ai_tally_result(
            v22_estimated_value=3,
            csv_ai_value=3,
            v3_ai_value=34,
            confidence="medium",
            target_cell_found=True,
            visible_mark_type="tally",
            page_id="P14"
        )
        # OCR correction detected: v22 fixed v3's error and matches CSV
        assert result.classification == AITallyClassification.OCR_CORRECTION
        assert "補正" in result.display_message or "改善" in result.display_message or "読取" in result.display_message
        # Should show v3 and v22 values to illustrate the correction
        assert "34" in result.display_message or "3" in result.display_message


def run_all_tests():
    """Run all tests manually if pytest not available."""
    test_classes = [
        TestNormalizeValue,
        TestCompareWithCSV,
        TestBuildReviewFlags,
        TestClassifyAutoConfirm,
        TestClassifyReviewRequired,
        TestMutualExclusion,
        TestDisplayMessages,
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for test_class in test_classes:
        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith("test_")]

        for method_name in methods:
            total_tests += 1
            try:
                method = getattr(instance, method_name)
                method()
                passed_tests += 1
                print(f"[PASS] {test_class.__name__}.{method_name}")
            except AssertionError as e:
                failed_tests.append((test_class.__name__, method_name, str(e)))
                print(f"[FAIL] {test_class.__name__}.{method_name}: {e}")
            except Exception as e:
                failed_tests.append((test_class.__name__, method_name, str(e)))
                print(f"[FAIL] {test_class.__name__}.{method_name}: {type(e).__name__}: {e}")

    print(f"\n{'='*60}")
    print(f"Total: {total_tests} | Passed: {passed_tests} | Failed: {len(failed_tests)}")

    if failed_tests:
        print(f"\nFailed tests:")
        for class_name, method_name, error in failed_tests:
            print(f"  - {class_name}.{method_name}")
            print(f"    {error}")
        return False
    else:
        print("\n[SUCCESS] All tests passed!")
        return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
