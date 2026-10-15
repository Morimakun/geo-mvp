"""Phase 6: 段階的フォールバック（staged fallback）パイプライン。

設計（2026-10-16）:
- FIRST PASS: 既存のページ単位まとめ読み（run_vision_evidence_pilot_page）をそのまま使う。
- 店舗コード・合計欄を、TRUSTED（first pass をそのまま採用）か FALLBACK_REQUIRED に分類する。
- FALLBACK: 対象フィールドだけ、画像表現を変えた2系統（A: 現行 crop、B: 広い crop）で
  専用 prompt により読み直す。A と B が一致し、マスター・CSV の条件をすべて満たす時だけ AUTO。
- 補正は一切しない（AU1K の付与、O/0・I/1 変換、桁補完、fuzzy/nearest は禁止）。
- JSON 解析に失敗した場合は、同じ画像で1回だけ repair 再試行する。それでも失敗なら REVIEW。
- 前回の結果を引き継がない（フォールバックは毎回、新しい読み取りだけを使う）。

このモジュールの判定関数は、読み取りを注入して呼ぶ（テストでは偽の reader を使う）。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

from src.phase6.direct_compare_gate import normalize_store_code

AUTO = "AUTO_MATCH"
REVIEW = "NEEDS_REVIEW"

STORE_PROMPT = (
    "この画像は手書きFAX帳票の店舗コード欄です。印刷済みの接頭辞 'AU1K' と、その後に並ぶ7つの手書き枠が写っています。\n"
    "1) 印刷されている接頭辞の文字をそのまま読んでください（写っていなければ空文字）。\n"
    "2) 各枠の文字を左から1枠ずつ読んでください。判読できない枠は '?' としてください。\n"
    "3) 推測で補完・修正しないでください。\n"
    "回答は次のJSONだけにしてください: {\"prefix\": \"...\", \"boxes\": [\"..\", \"..\", ...]}"
)

TOTAL_PROMPT = (
    "この画像は手書きFAX帳票の合計欄（数字を書く欄）です。次のどれかを判定し、JSONだけで答えてください。\n"
    "- \"number\": 数字が1つ書かれていて、読める（0 は丸い輪、1 は細い斜めの線）。value に整数。\n"
    "- \"empty\": 何も書かれていない（空欄）。value は null。0 と書かれている場合は empty にしない。\n"
    "- \"struck\": 数字の上に取り消し線・斜線がある。value は null（取り消された数字を確定しない）。\n"
    "- \"unreadable\": 何か書かれているが判読できない。value は null。\n"
    "推測で補完しないでください。回答形式: {\"state\": \"...\", \"value\": 数字またはnull}"
)

REPAIR_SUFFIX = "\n注意：前回の回答はJSONとして解釈できませんでした。説明文を付けず、JSONオブジェクトだけを返してください。"


# ---------------------------------------------------------------------------
# 純粋な判定ロジック
# ---------------------------------------------------------------------------

@dataclass
class DayRow:
    store_code: str
    intro: Optional[int]
    voice: Optional[int]


@dataclass
class ReadResult:
    ok: bool  # JSON 解析に成功したか
    data: dict[str, Any] = field(default_factory=dict)


class StagedReader(Protocol):
    """Vision 呼び出しの境界。テストでは偽の実装を注入する。"""

    def first_pass(self, page_no: int) -> dict[str, Any]: ...
    def store_read(self, page_no: int, variant: str) -> ReadResult: ...
    def total_read(self, page_no: int, field_name: str, variant: str) -> ReadResult: ...


def _norm(raw: Optional[str]) -> Optional[str]:
    """前後・内部の空白の除去と大文字化だけ（補正なし）。"""
    return normalize_store_code(raw)


def decide_store(
    *,
    page_no: int,
    first_raw: Optional[str],
    first_conf: Optional[str],
    day_rows: list[DayRow],
    valid_codes: set[str],
    reader: StagedReader,
) -> dict[str, Any]:
    norm = _norm(first_raw)
    csv_match = [r for r in day_rows if r.store_code == norm] if norm else []
    trusted = (
        first_conf == "high"
        and norm is not None
        and norm in valid_codes
        and len(csv_match) == 1
    )
    if trusted:
        return {"decision": AUTO, "source": "first_pass", "value": norm, "reasons": [], "fallback": None}

    fb: dict[str, Any] = {"A": None, "B": None}
    # 同じ当日 CSV に複数行 → 自動解決しない（フォールバックの読み直しも行わない）
    if norm and sum(1 for r in day_rows if r.store_code == norm) > 1:
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["csv_duplicate_rows"], "fallback": fb}

    a = reader.store_read(page_no, "A")
    b = reader.store_read(page_no, "B")
    fb["A"] = {"ok": a.ok, "raw": a.data.get("_raw")}
    fb["B"] = {"ok": b.ok, "raw": b.data.get("_raw")}
    if not (a.ok and b.ok):
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["store_json_parse_failed"], "fallback": fb}
    na, nb = _norm(a.data.get("_raw")), _norm(b.data.get("_raw"))
    if na is None or na != nb:
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["store_disagreement"], "fallback": fb}
    if na not in valid_codes:
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["store_not_in_master"], "fallback": fb}
    rows = [r for r in day_rows if r.store_code == na]
    if len(rows) != 1:
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["store_csv_not_unique" if rows else "store_not_in_day_csv"], "fallback": fb}
    return {"decision": AUTO, "source": "fallback", "value": na, "reasons": [], "fallback": fb}


def decide_total(
    *,
    page_no: int,
    field_name: str,
    first: dict[str, Any],
    csv_value: Optional[int],
    store_auto: bool,
    reader: StagedReader,
) -> dict[str, Any]:
    if not store_auto:
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["store_not_auto"], "fallback": None}
    if csv_value is None:
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["csv_value_missing"], "fallback": None}

    fv = first.get("value")
    if (first.get("status") == "observed" and first.get("confidence") == "high"
            and isinstance(fv, int) and fv == csv_value):
        return {"decision": AUTO, "source": "first_pass", "value": fv, "reasons": [], "fallback": None}

    a = reader.total_read(page_no, field_name, "A")
    b = reader.total_read(page_no, field_name, "B")
    fb = {"A": {"ok": a.ok, "state": a.data.get("state"), "value": a.data.get("value")},
          "B": {"ok": b.ok, "state": b.data.get("state"), "value": b.data.get("value")}}
    if not (a.ok and b.ok):
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["total_json_parse_failed"], "fallback": fb}
    if a.data.get("state") != "number" or b.data.get("state") != "number":
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["total_not_number_in_fallback"], "fallback": fb}
    va, vb = a.data.get("value"), b.data.get("value")
    if not (isinstance(va, int) and va == vb):
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["total_disagreement"], "fallback": fb}
    if va != csv_value:
        return {"decision": REVIEW, "source": "none", "value": None,
                "reasons": ["total_csv_mismatch"], "fallback": fb}
    return {"decision": AUTO, "source": "fallback", "value": va, "reasons": [], "fallback": fb}


def process_page(
    *,
    page_no: int,
    day_rows: list[DayRow],
    valid_codes: set[str],
    reader: StagedReader,
) -> dict[str, Any]:
    first = reader.first_pass(page_no)
    st = decide_store(
        page_no=page_no,
        first_raw=first["store"].get("raw"),
        first_conf=first["store"].get("conf"),
        day_rows=day_rows,
        valid_codes=valid_codes,
        reader=reader,
    )
    store_auto = st["decision"] == AUTO
    rows = {r.store_code: r for r in day_rows}
    matched = rows.get(st["value"]) if store_auto else None
    out: dict[str, Any] = {"page": page_no, "store": st, "fields": {}}
    for name, key, csv_idx in [("intro", "intro", "intro"), ("voice", "voice", "voice")]:
        csv_value = None
        if matched is not None:
            csv_value = matched.intro if csv_idx == "intro" else matched.voice
        out["fields"][name] = decide_total(
            page_no=page_no,
            field_name=f"{key}_written_total_region",
            first=first[name],
            csv_value=csv_value,
            store_auto=store_auto,
            reader=reader,
        )
    return out


def parse_json_object(text: str) -> Optional[dict[str, Any]]:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        j = json.loads(m.group(0))
    except Exception:
        return None
    return j if isinstance(j, dict) else None
