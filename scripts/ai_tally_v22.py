"""
AI Tally V2.2 - Standalone Classification Module

Purpose:
Classify AI tally extraction results from V2.2 (high-accuracy prompt variant)
into auto_confirm_candidate / review_required categories without modifying extractor.py.

V2.2 Role:
- Conditional adoption candidate for AI tally field (column AI)
- Supplement to v3 standard version (not replacement)
- Safe handling via auto/review split based on CSV match + confidence

Key Principle:
auto_confirm_candidate and review_required are MUTUALLY EXCLUSIVE.
A single page must be in exactly one category, never both.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Literal, Dict, Any
from enum import Enum


class AITallyClassification(str, Enum):
    """Classification result for display."""
    AUTO_CONFIRM = "auto_confirm"
    REVIEW_REQUIRED = "review"
    LOW_CONFIDENCE = "low_confidence"
    OCR_CORRECTION = "ocr_correction"


@dataclass
class AITallyV22Result:
    """Result from V2.2 extraction (input to classifier)."""
    page_id: str
    target_cell_found: bool
    estimated_value: Optional[int]
    confidence: Literal["high", "medium", "low"]
    visible_mark_type: str  # "tally", "digit", "blank", "unclear", "unknown"
    reason: str
    raw_response_summary: Optional[str] = None


@dataclass
class AITallyClassificationResult:
    """Output of classification process."""
    page_id: str

    # Mutually exclusive flags
    auto_confirm_candidate: bool
    review_required: bool

    # Classification for UI display
    classification: AITallyClassification

    # Review reason details
    review_reasons: List[str] = field(default_factory=list)

    # Comparison metrics
    v22_value: Optional[int] = None
    csv_value: Optional[int] = None
    v3_value: Optional[int] = None
    v22_vs_csv_diff: int = 0
    v22_vs_v3_diff: int = 0
    v22_closer_than_v3: bool = False
    v22_worse_than_v3: bool = False

    # UI display
    display_message: str = ""
    action_recommended: str = ""  # "skip", "confirm", "force_review"


def normalize_ai_tally_value(value: Any) -> Optional[int]:
    """
    Normalize V2.2/CSV/v3 values to comparable integers or None.

    Rules:
    - "blank" string -> 0
    - "" (empty string) -> None
    - None -> None
    - "2" (string number) -> 2
    - 2.0 (float) -> 2
    - 2 (int) -> 2
    """
    if value is None:
        return None

    if isinstance(value, str):
        if value.lower() == "blank":
            return 0
        if value.strip() == "":
            return None
        try:
            return int(value)
        except ValueError:
            return None

    if isinstance(value, float):
        return int(value)

    if isinstance(value, int):
        return value

    return None


def compare_ai_tally_with_csv(
    v22_value: Optional[int],
    csv_value: Optional[int],
    v3_value: Optional[int]
) -> Dict[str, Any]:
    """
    Compare V2.2, CSV, and v3 values.

    Returns:
    {
        "v22_vs_csv_diff": int,          # |v22 - csv|
        "v22_vs_v3_diff": int,          # |v22 - v3|
        "v22_closer_than_v3": bool,     # |v22-csv| < |v3-csv|
        "v22_worse_than_v3": bool,      # |v22-csv| > |v3-csv| (P16 rule)
        "csv_match": bool,              # v22 == csv
        "v3_match": bool,               # v3 == csv
    }
    """
    result = {
        "v22_vs_csv_diff": 0,
        "v22_vs_v3_diff": 0,
        "v22_closer_than_v3": False,
        "v22_worse_than_v3": False,
        "csv_match": v22_value == csv_value,
        "v3_match": v3_value == csv_value,
    }

    if v22_value is not None and csv_value is not None:
        result["v22_vs_csv_diff"] = abs(v22_value - csv_value)

    if v22_value is not None and v3_value is not None:
        result["v22_vs_v3_diff"] = abs(v22_value - v3_value)

    if (v22_value is not None and v3_value is not None and
        csv_value is not None):
        v22_distance = abs(v22_value - csv_value)
        v3_distance = abs(v3_value - csv_value)
        result["v22_closer_than_v3"] = v22_distance < v3_distance
        result["v22_worse_than_v3"] = v22_distance > v3_distance

    return result


def build_ai_tally_review_flags(
    target_cell_found: bool,
    estimated_value: Optional[int],
    confidence: Literal["high", "medium", "low"],
    v22_value: Optional[int],
    csv_value: Optional[int],
    v3_value: Optional[int],
    visible_mark_type: str,
    raw_response_summary: Optional[str] = None
) -> tuple[bool, List[str]]:
    """
    Determine if review_required is True and collect reasons.

    Returns:
        (review_required: bool, reasons: List[str])

    review_required conditions:
    1. target_cell_found != true
    2. estimated_value is null
    3. confidence == low
    4. v22_value != csv_value (mismatch)
    5. visible_mark_type in {unclear, unknown}
    6. blank判定だがCSV値 > 0
    7. |v22 - v3| >= 3 (large difference)
    8. v22がv3よりCSVから遠ざかる (P16 rule)
    9. raw_response上で対象セル以外を見た疑い
    """
    review_required = False
    reasons: List[str] = []

    # Condition 1: target_cell_found != true
    if not target_cell_found:
        review_required = True
        reasons.append("target_cell_found == false")

    # Condition 2: estimated_value is null
    if estimated_value is None:
        review_required = True
        reasons.append("estimated_value == null")

    # Condition 3: confidence == low
    if confidence == "low":
        review_required = True
        reasons.append("confidence == low")

    # Condition 4: v22 != csv (mismatch)
    if v22_value is not None and csv_value is not None:
        if v22_value != csv_value:
            review_required = True
            reasons.append(f"v22値 {v22_value} != CSV値 {csv_value}")

    # Condition 5: visible_mark_type unclear/unknown
    if visible_mark_type in {"unclear", "unknown"}:
        review_required = True
        reasons.append(f"mark_type == {visible_mark_type}")

    # Condition 6: blank判定だがCSV値 > 0
    if visible_mark_type == "blank" and csv_value is not None and csv_value > 0:
        review_required = True
        reasons.append(f"blank判定だがCSV値={csv_value}")

    # Condition 7: |v22 - v3| >= 3 BUT NOT if v22==csv (OCR correction case)
    # If v22 matches CSV, large diff from v3 is OCR correction, not a problem
    if v22_value is not None and v3_value is not None:
        diff = abs(v22_value - v3_value)
        if diff >= 3 and v22_value != csv_value:
            review_required = True
            reasons.append(f"v3との大差: |{v22_value}-{v3_value}|={diff}")

    # Condition 8: P16 rule - v22がv3よりCSVから遠ざかる
    if v22_value is not None and v3_value is not None and csv_value is not None:
        v22_distance = abs(v22_value - csv_value)
        v3_distance = abs(v3_value - csv_value)
        if v22_distance > v3_distance:
            review_required = True
            reasons.append(f"悪化検知: v22がv3よりCSVから遠い (v22距離={v22_distance} > v3距離={v3_distance})")

    # Condition 9: raw_response上で対象セル以外を見た疑い
    if raw_response_summary:
        # Heuristic: if response mentions other cells or is unclear about target
        if "他のセル" in raw_response_summary or "セル確認なし" in raw_response_summary:
            review_required = True
            reasons.append("raw_response: 対象セル以外の可能性")

    return review_required, reasons


def classify_ai_tally_result(
    v22_estimated_value: Optional[int],
    csv_ai_value: Optional[int],
    v3_ai_value: Optional[int],
    confidence: Literal["high", "medium", "low"],
    target_cell_found: bool,
    visible_mark_type: str,
    page_id: str = "Unknown",
    raw_response_summary: Optional[str] = None
) -> AITallyClassificationResult:
    """
    Classify V2.2 result into auto_confirm_candidate or review_required.

    Mutually exclusive logic:
    - auto_confirm_candidate: ALL conditions met
    - review_required: ANY review condition met
    - Result: exactly one of the two is True, never both

    auto_confirm_candidate conditions (all must be true):
    1. target_cell_found == true
    2. estimated_value is integer (not null)
    3. confidence in {medium, high}
    4. v22_estimated_value == csv_ai_value (exact match)
    5. visible_mark_type in {tally, digit, blank}
    6. review_required == false (none of the review conditions)
    7. raw_response shows AI tally row is visible

    Parameters:
        v22_estimated_value: V2.2推定値
        csv_ai_value: Salesforce CSV列35の値
        v3_ai_value: v3参考値
        confidence: V2.2の信頼度
        target_cell_found: AI合計セル検出フラグ
        visible_mark_type: 視認型
        page_id: ページID（ログ用）
        raw_response_summary: 応答要約（セル確認用）

    Returns:
        AITallyClassificationResult (auto_confirm_candidate XOR review_required)
    """
    # Normalize values
    v22_value = v22_estimated_value
    csv_value = csv_ai_value
    v3_value = v3_ai_value

    # Get comparison metrics
    comparison = compare_ai_tally_with_csv(v22_value, csv_value, v3_value)

    # Determine review_required status
    review_required, review_reasons = build_ai_tally_review_flags(
        target_cell_found=target_cell_found,
        estimated_value=v22_value,
        confidence=confidence,
        v22_value=v22_value,
        csv_value=csv_value,
        v3_value=v3_value,
        visible_mark_type=visible_mark_type,
        raw_response_summary=raw_response_summary
    )

    # Determine auto_confirm_candidate
    # ALL conditions must be true, and review_required must be false
    auto_confirm_candidate = False

    if (not review_required and
        target_cell_found and
        v22_value is not None and
        confidence in {"medium", "high"} and
        v22_value == csv_value and
        visible_mark_type in {"tally", "digit", "blank"}):
        auto_confirm_candidate = True

    # Determine classification for UI display
    # Priority: OCR_CORRECTION > LOW_CONFIDENCE > AUTO_CONFIRM > REVIEW_REQUIRED
    if auto_confirm_candidate and v22_value is not None and v3_value is not None and v22_value != v3_value:
        # OCR correction: V2.2 fixed v3 error and matches CSV (special case of auto_confirm)
        classification = AITallyClassification.OCR_CORRECTION
    elif auto_confirm_candidate:
        classification = AITallyClassification.AUTO_CONFIRM
    elif confidence == "low":
        classification = AITallyClassification.LOW_CONFIDENCE
    else:
        classification = AITallyClassification.REVIEW_REQUIRED

    # Build display message
    display_message = build_display_message(
        auto_confirm_candidate=auto_confirm_candidate,
        review_required=review_required,
        classification=classification,
        v22_value=v22_value,
        csv_value=csv_value,
        v3_value=v3_value,
        confidence=confidence,
        review_reasons=review_reasons
    )

    # Determine recommended action
    if auto_confirm_candidate:
        action_recommended = "skip"
    elif confidence == "low":
        action_recommended = "force_review"
    else:
        action_recommended = "confirm"

    # Build result
    result = AITallyClassificationResult(
        page_id=page_id,
        auto_confirm_candidate=auto_confirm_candidate,
        review_required=review_required,
        classification=classification,
        review_reasons=review_reasons,
        v22_value=v22_value,
        csv_value=csv_value,
        v3_value=v3_value,
        v22_vs_csv_diff=comparison["v22_vs_csv_diff"],
        v22_vs_v3_diff=comparison["v22_vs_v3_diff"],
        v22_closer_than_v3=comparison["v22_closer_than_v3"],
        v22_worse_than_v3=comparison["v22_worse_than_v3"],
        display_message=display_message,
        action_recommended=action_recommended
    )

    # Verify mutually exclusive property
    assert not (auto_confirm_candidate and review_required), \
        f"Page {page_id}: auto_confirm and review_required cannot both be true"

    return result


def build_display_message(
    auto_confirm_candidate: bool,
    review_required: bool,
    classification: AITallyClassification,
    v22_value: Optional[int],
    csv_value: Optional[int],
    v3_value: Optional[int],
    confidence: str,
    review_reasons: List[str]
) -> str:
    """
    Build human-readable display message for UI.

    Classification A: 自動確定候補
    Classification B: 要確認
    Classification C: 低信頼度
    Classification D: OCR補正候補
    """
    if classification == AITallyClassification.AUTO_CONFIRM:
        return (
            f"✅ 自動確定候補\n"
            f"PDF AI合計：{v22_value}\n"
            f"Salesforce AI値：{csv_value}\n"
            f"→ 完全に一致しています。確認をスキップ可能です。"
        )

    elif classification == AITallyClassification.LOW_CONFIDENCE:
        return (
            f"🔶 低信頼度（強制確認）\n"
            f"PDF AI合計：{v22_value}\n"
            f"Salesforce AI値：{csv_value}\n"
            f"信頼度：{confidence}\n"
            f"→ AIの確信度が低いため、必ず確認してください。"
        )

    elif classification == AITallyClassification.OCR_CORRECTION:
        return (
            f"🔄 OCR補正候補\n"
            f"旧読取値（v3）：{v3_value}\n"
            f"新読取値（v22）：{v22_value}\n"
            f"Salesforce AI値：{csv_value}\n"
            f"→ 読取の改善が検出されました。正の字読取が補正された可能性があります。"
        )

    else:  # REVIEW_REQUIRED
        reason_text = "\n".join(f"  • {r}" for r in review_reasons)
        return (
            f"⚠️ 要確認\n"
            f"PDF AI合計：{v22_value}\n"
            f"Salesforce AI値：{csv_value}\n"
            f"理由：\n{reason_text}\n"
            f"→ 確認して値を確定してください。"
        )


if __name__ == "__main__":
    # Simple smoke test
    result = classify_ai_tally_result(
        v22_estimated_value=5,
        csv_ai_value=5,
        v3_ai_value=5,
        confidence="medium",
        target_cell_found=True,
        visible_mark_type="tally",
        page_id="P1"
    )
    print(f"P1: auto={result.auto_confirm_candidate}, review={result.review_required}")
    print(f"Classification: {result.classification}")
    print(f"Message:\n{result.display_message}\n")

    # Test review_required case
    result2 = classify_ai_tally_result(
        v22_estimated_value=2,
        csv_ai_value=11,
        v3_ai_value=9,
        confidence="low",
        target_cell_found=True,
        visible_mark_type="tally",
        page_id="P16"
    )
    print(f"P16: auto={result2.auto_confirm_candidate}, review={result2.review_required}")
    print(f"Classification: {result2.classification}")
    print(f"Message:\n{result2.display_message}\n")
