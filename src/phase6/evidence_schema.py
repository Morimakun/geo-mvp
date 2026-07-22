"""Phase 6: Vision抽出結果を保持するためのevidenceスキーマ（Step 2 / evidence schema）。

設計根拠: docs/PHASE_6_TRIPLE_EVIDENCE_SCHEMA_DESIGN_REVIEW.md 第4版

このモジュールの責務は「紹介/お声がけの記載合計・正の字・店舗コードのVision抽出結果を、
安全に保持できるデータの器を定義する」ことに限定される。
Visionプロンプトの実装・実際の抽出処理・店舗コードの正規化や近似探索・CSV照合・
三者比較・review routing・UIには一切関与しない（それらは別モジュール・別Stepの責務）。

正本（single source of truth）:
    intro_evidence.written_total.value
    voice_evidence.written_total.value

旧項目名 intro_total / voice_callout_total は独立して保持しない。
PageEvidence.intro_total / voice_callout_total はいずれも上記正本から派生する
property であり、二重管理は行わない。旧形式のJSONを取り込む場合は
PageEvidence.from_legacy_dict() を明示的に使用すること。

スコープ外（意図的に扱わない）:
    - CSV候補行の検索・一意解決（Step 1 / csv_candidate_resolver.py の責務）。
    - 店舗コードの正規化・近似探索・CSVとの照合（将来のStepの責務）。
    - written_total / tally_count / csv値の三者比較（将来のStepの責務）。
    - review routing・UI表示。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

__all__ = [
    "EvidenceValidationError",
    "EvidenceStatus",
    "Confidence",
    "TallyObservationStatus",
    "StoreCodeFormatStatus",
    "WrittenTotalEvidence",
    "TallyComponent",
    "TallyEvidence",
    "NumericFieldEvidence",
    "StoreCodeEvidence",
    "PageEvidence",
]


class EvidenceValidationError(Exception):
    """このモジュールが送出する、evidence構造の不整合に対する例外。"""


# ============================================================
# 列挙型
# ============================================================
class EvidenceStatus(str, Enum):
    """WrittenTotalEvidence.status / StoreCodeEvidence.status で共通利用する、
    「その項目がどう観測されたか」を表す5状態。

    NOT_OBSERVED: 項目は存在・適用する可能性があるが、旧スキーマまたは旧処理では
    観測・抽出されていない（＝分からない）。NO_VALUE（実際に空欄と確認済み）や
    NOT_APPLICABLE（この帳票版には項目自体が存在しない）とは区別すること。
    """

    OBSERVED = "observed"
    NO_VALUE = "no_value"
    UNREADABLE = "unreadable"
    NOT_APPLICABLE = "not_applicable"
    NOT_OBSERVED = "not_observed"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TallyObservationStatus(str, Enum):
    """NOT_OBSERVEDの定義はEvidenceStatusと同様
    （旧スキーマ/旧処理では観測・抽出されていない＝分からない）。"""

    MARKS_PRESENT = "marks_present"
    NO_MARKS_OBSERVED = "no_marks_observed"
    UNREADABLE = "unreadable"
    NOT_APPLICABLE = "not_applicable"
    NOT_OBSERVED = "not_observed"


class StoreCodeFormatStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    UNKNOWN = "unknown"


# ============================================================
# ヘルパー: 正の字の数値バリデーション
# ============================================================
def _validate_five_and_remainder(complete_five_groups: int, remainder_strokes: int, *, context: str) -> None:
    if complete_five_groups < 0:
        raise EvidenceValidationError(
            f"{context}: complete_five_groupsは負数にできません: {complete_five_groups}"
        )
    if remainder_strokes < 0:
        raise EvidenceValidationError(
            f"{context}: remainder_strokesは負数にできません: {remainder_strokes}"
        )
    if not (0 <= remainder_strokes <= 4):
        raise EvidenceValidationError(
            f"{context}: remainder_strokesは0〜4の範囲である必要があります: {remainder_strokes}"
        )


# ============================================================
# WrittenTotalEvidence（記載された合計数字そのもの）
# ============================================================
@dataclass(frozen=True)
class WrittenTotalEvidence:
    value: Optional[int]
    status: EvidenceStatus
    confidence: Optional[Confidence] = None
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if self.status == EvidenceStatus.OBSERVED:
            if self.value is None:
                raise EvidenceValidationError("status=observedの場合はvalueが必須です")
        elif self.value is not None:
            raise EvidenceValidationError(
                f"status={self.status.value}の場合はvalueを持たせられません"
                "（観測されていない項目にvalueを与えないでください）"
            )

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "status": self.status.value,
            "confidence": self.confidence.value if self.confidence is not None else None,
            "notes": self.notes,
        }


# ============================================================
# 正の字（tally）
# ============================================================
@dataclass(frozen=True)
class TallyComponent:
    """正の字の内訳1行分。complete_five_groups/remainder_strokesは
    行の内訳が判明している場合のみ生成すること（両方必須）。"""

    row_label: Optional[str]
    complete_five_groups: int
    remainder_strokes: int

    def __post_init__(self) -> None:
        _validate_five_and_remainder(
            self.complete_five_groups, self.remainder_strokes, context="TallyComponent"
        )

    @property
    def count(self) -> int:
        return self.complete_five_groups * 5 + self.remainder_strokes

    def to_dict(self) -> dict:
        return {
            "row_label": self.row_label,
            "complete_five_groups": self.complete_five_groups,
            "remainder_strokes": self.remainder_strokes,
            "count": self.count,
        }


@dataclass(frozen=True)
class TallyEvidence:
    observation_status: TallyObservationStatus
    complete_five_groups: Optional[int] = None
    remainder_strokes: Optional[int] = None
    confidence: Optional[Confidence] = None
    notes: Optional[str] = None
    components: list = field(default_factory=list)  # list[TallyComponent]

    def __post_init__(self) -> None:
        if self.observation_status == TallyObservationStatus.MARKS_PRESENT:
            if self.complete_five_groups is None or self.remainder_strokes is None:
                raise EvidenceValidationError(
                    "observation_status=marks_presentの場合は"
                    "complete_five_groupsとremainder_strokesの両方を数値化する必要があります"
                )
            _validate_five_and_remainder(
                self.complete_five_groups, self.remainder_strokes, context="TallyEvidence"
            )
        elif self.complete_five_groups is not None or self.remainder_strokes is not None:
            # marks_present以外（no_marks_observed/unreadable/not_applicable/not_observed）
            # では complete_five_groups=0 / remainder_strokes=0 へも変換しない。
            # 「画数を数えていない（None）」と「数えた結果0だった」は区別する。
            raise EvidenceValidationError(
                f"observation_status={self.observation_status.value}の場合は"
                "complete_five_groups/remainder_strokesを数値化できません"
                "（0への変換も含め、Noneのままにしてください）"
            )

        if self.components:
            component_sum = sum(c.count for c in self.components)
            if component_sum != self.tally_count:
                raise EvidenceValidationError(
                    f"componentsの合計({component_sum})と集約値tally_count"
                    f"({self.tally_count})が一致しません"
                )

    @property
    def tally_count(self) -> Optional[int]:
        if self.complete_five_groups is None or self.remainder_strokes is None:
            return None
        return self.complete_five_groups * 5 + self.remainder_strokes

    def to_dict(self) -> dict:
        return {
            "observation_status": self.observation_status.value,
            "complete_five_groups": self.complete_five_groups,
            "remainder_strokes": self.remainder_strokes,
            "tally_count": self.tally_count,
            "confidence": self.confidence.value if self.confidence is not None else None,
            "notes": self.notes,
            "components": [c.to_dict() for c in self.components],
        }


# ============================================================
# 紹介/お声がけ共通の数値項目コンテナ（intro_evidence / voice_evidenceそれぞれで
# 独立したインスタンスとして使用する）
# ============================================================
@dataclass(frozen=True)
class NumericFieldEvidence:
    written_total: WrittenTotalEvidence
    tally: TallyEvidence

    def to_dict(self) -> dict:
        return {
            "written_total": self.written_total.to_dict(),
            "tally": self.tally.to_dict(),
        }


# ============================================================
# 店舗コード（このStepでは値を保持するだけ。正規化・近似探索・CSV照合は行わない）
# ============================================================
@dataclass(frozen=True)
class StoreCodeEvidence:
    raw_value: Optional[str] = None
    normalized_value: Optional[str] = None
    status: EvidenceStatus = EvidenceStatus.NO_VALUE
    confidence: Optional[Confidence] = None
    format_status: StoreCodeFormatStatus = StoreCodeFormatStatus.UNKNOWN
    notes: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "status": self.status.value,
            "confidence": self.confidence.value if self.confidence is not None else None,
            "format_status": self.format_status.value,
            "notes": self.notes,
        }


# ============================================================
# ページ単位
# ============================================================
@dataclass(frozen=True)
class PageEvidence:
    page_no: int
    form_version: str
    selected_business_date: str  # 外部設定の正本。OCR日付ではない（Step 1と同じ扱い）
    store_code_evidence: StoreCodeEvidence
    intro_evidence: NumericFieldEvidence
    voice_evidence: NumericFieldEvidence

    @property
    def intro_total(self) -> Optional[int]:
        """旧項目名との後方互換のためのproperty。正本はintro_evidence.written_total.value。"""
        return self.intro_evidence.written_total.value

    @property
    def voice_callout_total(self) -> Optional[int]:
        """旧項目名との後方互換のためのproperty。正本はvoice_evidence.written_total.value。"""
        return self.voice_evidence.written_total.value

    def to_dict(self, *, include_legacy: bool = False) -> dict:
        result = {
            "page_no": self.page_no,
            "form_version": self.form_version,
            "selected_business_date": self.selected_business_date,
            "store_code_evidence": self.store_code_evidence.to_dict(),
            "intro_evidence": self.intro_evidence.to_dict(),
            "voice_evidence": self.voice_evidence.to_dict(),
        }
        if include_legacy:
            result["intro_total"] = self.intro_total
            result["voice_callout_total"] = self.voice_callout_total
        return result

    @classmethod
    def from_legacy_dict(cls, data: dict) -> "PageEvidence":
        """旧形式（intro_total/voice_callout_totalのみを持つフラットな辞書）から
        最小限のPageEvidenceを構築する明示的な変換関数。

        「旧JSONにキーが存在しない」ことを no_value / not_applicable へ自動変換しない。
        キーの有無・値・明示的なstatus上書きキーから、次の基準で判定する:

            - status上書きキー（例: store_code_status）が指定されている
              -> それを最優先で採用する（例: "この帳票版には項目自体が存在しない"
                 ことが呼び出し側で判明している場合に not_applicable を明示するため）。
            - 値キー自体がdataに存在しない -> NOT_OBSERVED
              （旧処理で未抽出・未保存。「分からない」という安全側のデフォルト）。
            - 値キーが存在するが値がNone -> NO_VALUE（実際に空欄と確認済み）。
            - 値キーが存在し値がNone以外 -> OBSERVED。

        tally情報は旧JSONに元々存在しないため、明示的な上書き
        （intro_tally_status / voice_tally_status）がない限り常にNOT_OBSERVED・
        tally_count=Noneとする。

        正本と旧項目を二重管理しないため、旧JSONの取り込みは必ずこの関数を経由すること。
        """

        def _classify(value_key: str, status_override_key: str) -> EvidenceStatus:
            override = data.get(status_override_key)
            if override is not None:
                return EvidenceStatus(override)
            if value_key not in data:
                return EvidenceStatus.NOT_OBSERVED
            if data[value_key] is None:
                return EvidenceStatus.NO_VALUE
            return EvidenceStatus.OBSERVED

        def _legacy_written_total(value_key: str, status_override_key: str) -> WrittenTotalEvidence:
            status = _classify(value_key, status_override_key)
            if status == EvidenceStatus.OBSERVED:
                return WrittenTotalEvidence(value=int(data[value_key]), status=status)
            return WrittenTotalEvidence(value=None, status=status)

        def _legacy_tally(status_override_key: str) -> TallyEvidence:
            override = data.get(status_override_key)
            status = (
                TallyObservationStatus(override)
                if override is not None
                else TallyObservationStatus.NOT_OBSERVED
            )
            return TallyEvidence(observation_status=status)

        store_code_status = _classify("store_code", "store_code_status")
        store_code = data.get("store_code") if store_code_status == EvidenceStatus.OBSERVED else None

        return cls(
            page_no=data["page_no"],
            form_version=data.get("form_version", "unknown"),
            selected_business_date=data["selected_business_date"],
            store_code_evidence=StoreCodeEvidence(
                raw_value=store_code,
                normalized_value=store_code,
                status=store_code_status,
            ),
            intro_evidence=NumericFieldEvidence(
                written_total=_legacy_written_total("intro_total", "intro_total_status"),
                tally=_legacy_tally("intro_tally_status"),
            ),
            voice_evidence=NumericFieldEvidence(
                written_total=_legacy_written_total("voice_callout_total", "voice_callout_total_status"),
                tally=_legacy_tally("voice_tally_status"),
            ),
        )
