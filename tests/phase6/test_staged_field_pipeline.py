"""段階的フォールバック判定（staged_field_pipeline）のテスト。偽の reader で Vision を置き換える。"""

from __future__ import annotations

from typing import Any

from src.phase6.staged_field_pipeline import (
    AUTO,
    REVIEW,
    DayRow,
    ReadResult,
    decide_store,
    decide_total,
    parse_json_object,
    process_page,
)

VALID = {"AU1K4050055", "AU1K4330093", "AU1KC400079", "AU1KB830201", "AU1KB830227"}
DAY = [
    DayRow("AU1K4050055", 0, 0),
    DayRow("AU1K4330093", 1, 0),
    DayRow("AU1KC400079", 2, 0),
    DayRow("AU1KB830201", 0, 0),
    DayRow("AU1KB830227", 5, 0),
    DayRow("AU1KB830227", 2, 0),  # 重複行
]


class FakeReader:
    """first / store A,B / total A,B の応答を用意して返す。呼び出し回数も数える。"""

    def __init__(self, first: dict[str, Any], store: dict[str, ReadResult] | None = None,
                 total: dict[tuple[str, str], ReadResult] | None = None) -> None:
        self.first_resp = first
        self.store_resp = store or {}
        self.total_resp = total or {}
        self.store_calls: list[str] = []
        self.total_calls: list[tuple[str, str]] = []

    def first_pass(self, page_no: int) -> dict[str, Any]:
        return self.first_resp

    def store_read(self, page_no: int, variant: str) -> ReadResult:
        self.store_calls.append(variant)
        return self.store_resp.get(variant, ReadResult(ok=True, data={"_raw": None}))

    def total_read(self, page_no: int, field_name: str, variant: str) -> ReadResult:
        self.total_calls.append((field_name, variant))
        return self.total_resp.get((field_name, variant), ReadResult(ok=True, data={"state": "unreadable", "value": None}))


def first(store_raw, store_conf="high", intro=(None, None), voice=(None, None)):
    return {
        "store": {"raw": store_raw, "conf": store_conf},
        "intro": {"status": intro[0], "value": intro[1], "confidence": "high"},
        "voice": {"status": voice[0], "value": voice[1], "confidence": "high"},
    }


def ok(raw):
    return ReadResult(ok=True, data={"_raw": raw})


def num(v):
    return ReadResult(ok=True, data={"state": "number", "value": v})


# ---- store ---------------------------------------------------------------

def test_first_pass_trusted_store_is_used_without_fallback():
    r = FakeReader(first("AU1K4050055", "high"))
    res = decide_store(page_no=59, first_raw="AU1K4050055", first_conf="high",
                       day_rows=DAY, valid_codes=VALID, reader=r)
    assert res["decision"] == AUTO and res["source"] == "first_pass"
    assert r.store_calls == []  # フォールバックを呼ばない


def test_first_pass_medium_confidence_goes_to_fallback():
    r = FakeReader(first("AU1KC400079", "medium"), store={"A": ok("AU1KC400079"), "B": ok("AU1KC400079")})
    res = decide_store(page_no=41, first_raw="AU1KC400079", first_conf="medium",
                       day_rows=DAY, valid_codes=VALID, reader=r)
    assert res["decision"] == AUTO and res["source"] == "fallback"
    assert r.store_calls == ["A", "B"]


def test_fallback_disagreement_is_review():
    r = FakeReader(first("AU1K405055", "high"), store={"A": ok("AU1K4050055"), "B": ok("AU1K4050050")})
    res = decide_store(page_no=59, first_raw="AU1K405055", first_conf="high",
                       day_rows=DAY, valid_codes=VALID, reader=r)
    assert res["decision"] == REVIEW and "store_disagreement" in res["reasons"]


def test_fallback_exact_but_master_miss_is_review():
    r = FakeReader(first("AU1K9999999", "medium"), store={"A": ok("AU1K9999999"), "B": ok("AU1K9999999")})
    res = decide_store(page_no=1, first_raw="AU1K9999999", first_conf="medium",
                       day_rows=DAY, valid_codes=VALID, reader=r)
    assert res["decision"] == REVIEW and "store_not_in_master" in res["reasons"]


def test_duplicate_csv_rows_review_without_fallback():
    r = FakeReader(first("AU1KB830227", "high"))
    res = decide_store(page_no=9, first_raw="AU1KB830227", first_conf="high",
                       day_rows=DAY, valid_codes=VALID, reader=r)
    assert res["decision"] == REVIEW and "csv_duplicate_rows" in res["reasons"]
    assert r.store_calls == []


def test_store_json_failure_is_review_not_guessed():
    r = FakeReader(first("AU1K405055", "medium"), store={"A": ReadResult(False, {}), "B": ok("AU1K4050055")})
    res = decide_store(page_no=59, first_raw="AU1K405055", first_conf="medium",
                       day_rows=DAY, valid_codes=VALID, reader=r)
    assert res["decision"] == REVIEW and "store_json_parse_failed" in res["reasons"]


def test_no_auto_prefix_or_o0_correction():
    # 接頭辞欠落・O/0 誤読は、そのまま扱う（補完・置換しない）
    r = FakeReader(first("B830201", "high"), store={"A": ok("B830201"), "B": ok("B830201")})
    res = decide_store(page_no=5, first_raw="B830201", first_conf="high",
                       day_rows=DAY, valid_codes=VALID, reader=r)
    assert res["decision"] == REVIEW
    r2 = FakeReader(first("AU1K433O093", "high"), store={"A": ok("AU1K433O093"), "B": ok("AU1K433O093")})
    res2 = decide_store(page_no=32, first_raw="AU1K433O093", first_conf="high",
                        day_rows=DAY, valid_codes=VALID, reader=r2)
    assert res2["decision"] == REVIEW and res2["value"] is None


# ---- totals -------------------------------------------------------------

def test_total_first_pass_high_number_matching_csv_is_auto():
    res = decide_total(page_no=59, field_name="intro_written_total_region",
                       first={"status": "observed", "value": 0, "confidence": "high"},
                       csv_value=0, store_auto=True, reader=FakeReader({}))
    assert res["decision"] == AUTO and res["source"] == "first_pass"


def test_total_medium_goes_to_fallback_and_auto_only_when_both_agree():
    r = FakeReader({}, total={("voice_written_total_region", "A"): num(0),
                              ("voice_written_total_region", "B"): num(0)})
    res = decide_total(page_no=59, field_name="voice_written_total_region",
                       first={"status": "observed", "value": 0, "confidence": "medium"},
                       csv_value=0, store_auto=True, reader=r)
    assert res["decision"] == AUTO and res["source"] == "fallback"


def test_total_store_not_auto_skips_all_reads():
    r = FakeReader({})
    res = decide_total(page_no=59, field_name="intro_written_total_region",
                       first={"status": "observed", "value": 0, "confidence": "high"},
                       csv_value=0, store_auto=False, reader=r)
    assert res["decision"] == REVIEW and "store_not_auto" in res["reasons"]
    assert r.total_calls == []


def test_zero_vs_blank_is_not_conflated():
    # first pass で no_value（空欄扱い）でも、フォールバックが number 0 なら AUTO 可能。
    # 逆に、フォールバックが empty を返せば空欄として REVIEW（0 にしない）
    r_empty = FakeReader({}, total={
        ("intro_written_total_region", "A"): ReadResult(True, {"state": "empty", "value": None}),
        ("intro_written_total_region", "B"): ReadResult(True, {"state": "empty", "value": None}),
    })
    res = decide_total(page_no=59, field_name="intro_written_total_region",
                       first={"status": "no_value", "value": None, "confidence": "high"},
                       csv_value=0, store_auto=True, reader=r_empty)
    assert res["decision"] == REVIEW and "total_not_number_in_fallback" in res["reasons"]


def test_strikethrough_is_not_confirmed():
    r = FakeReader({}, total={
        ("intro_written_total_region", "A"): ReadResult(True, {"state": "struck", "value": None}),
        ("intro_written_total_region", "B"): ReadResult(True, {"state": "struck", "value": None}),
    })
    res = decide_total(page_no=16, field_name="intro_written_total_region",
                       first={"status": "unreadable", "value": None, "confidence": "low"},
                       csv_value=6, store_auto=True, reader=r)
    assert res["decision"] == REVIEW


def test_total_fallback_disagreement_and_csv_mismatch_are_review():
    r = FakeReader({}, total={("intro_written_total_region", "A"): num(1),
                              ("intro_written_total_region", "B"): num(2)})
    res = decide_total(page_no=32, field_name="intro_written_total_region",
                       first={"status": "unreadable", "value": None, "confidence": "low"},
                       csv_value=1, store_auto=True, reader=r)
    assert res["decision"] == REVIEW and "total_disagreement" in res["reasons"]

    r2 = FakeReader({}, total={("intro_written_total_region", "A"): num(3),
                               ("intro_written_total_region", "B"): num(3)})
    res2 = decide_total(page_no=32, field_name="intro_written_total_region",
                        first={"status": "unreadable", "value": None, "confidence": "low"},
                        csv_value=1, store_auto=True, reader=r2)
    assert res2["decision"] == REVIEW and "total_csv_mismatch" in res2["reasons"]


def test_total_json_failure_is_review():
    r = FakeReader({}, total={("voice_written_total_region", "A"): ReadResult(False, {}),
                              ("voice_written_total_region", "B"): num(0)})
    res = decide_total(page_no=5, field_name="voice_written_total_region",
                       first={"status": "no_value", "value": None, "confidence": "medium"},
                       csv_value=0, store_auto=True, reader=r)
    assert res["decision"] == REVIEW and "total_json_parse_failed" in res["reasons"]


def test_previous_first_pass_value_does_not_leak_into_fallback():
    # first pass は 9 と言うが、フォールバックが 0 と読めば、判定は 0 のフォールバック結果に基づく（first は使わない）
    r = FakeReader({}, total={("intro_written_total_region", "A"): num(0),
                              ("intro_written_total_region", "B"): num(0)})
    res = decide_total(page_no=59, field_name="intro_written_total_region",
                       first={"status": "observed", "value": 9, "confidence": "medium"},
                       csv_value=0, store_auto=True, reader=r)
    assert res["decision"] == AUTO and res["value"] == 0


# ---- page-level ----------------------------------------------------------

def test_page_pipeline_auto_for_trusted_store_and_totals():
    f = first("AU1K4050055", "high", intro=("observed", 0), voice=("observed", 0))
    r = FakeReader(f)
    res = process_page(page_no=59, day_rows=DAY, valid_codes=VALID, reader=r)
    assert res["store"]["decision"] == AUTO
    assert res["fields"]["intro"]["decision"] == AUTO
    assert res["fields"]["voice"]["decision"] == AUTO
    assert r.store_calls == [] and r.total_calls == []  # 全て first pass のみ


def test_parse_json_object_rejects_non_object():
    assert parse_json_object("no json here") is None
    assert parse_json_object('{"state": "number", "value": 1}') == {"state": "number", "value": 1}
