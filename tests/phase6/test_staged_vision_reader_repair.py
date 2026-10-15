"""StagedVisionReader の JSON format-repair 再試行（API は偽物で置き換える）。"""

from datetime import date
from pathlib import Path
from types import SimpleNamespace

from src.phase6.staged_vision_reader import StagedVisionReader


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def create(self, **kwargs):
        self.prompts.append(kwargs["messages"][0]["content"][1]["text"])
        text = self.replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


def make_reader(replies):
    fake = SimpleNamespace(messages=FakeMessages(replies))
    reader = StagedVisionReader(client=fake, run_id="t", selected_day=date(2026, 6, 26),
                                output_dir=Path("."))
    return reader, fake


def test_repair_retry_recovers_when_second_reply_is_json():
    reader, fake = make_reader(["読み取り結果は次の通りです…", '{"state": "number", "value": 2}'])
    r = reader._read_json(b"img", "PROMPT", "total_fallback")
    assert r.ok and r.data == {"state": "number", "value": 2}
    assert reader.calls["repair_retry"] == 1
    assert "JSONとして解釈できませんでした" in fake.messages.prompts[1]  # 形式の修復だけを依頼する


def test_repair_retry_failure_is_not_ok():
    reader, _ = make_reader(["not json", "still not json"])
    r = reader._read_json(b"img", "PROMPT", "store_fallback")
    assert r.ok is False
    assert reader.calls["repair_retry"] == 1


def test_no_retry_when_first_reply_is_json():
    reader, _ = make_reader(['{"state": "empty", "value": null}'])
    r = reader._read_json(b"img", "PROMPT", "total_fallback")
    assert r.ok and r.data["state"] == "empty"
    assert reader.calls["repair_retry"] == 0
