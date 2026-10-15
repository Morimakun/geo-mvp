"""段階的フォールバック用の実 Vision reader（staged_field_pipeline の StagedReader 実装）。

- first_pass: 既存のページ単位まとめ読み（run_vision_evidence_pilot_page）をそのまま使う。
- store_read / total_read: 専用 prompt による単独呼び出し。A は現行 crop、B は広い crop。
- JSON 解析に失敗したら、同じ画像で1回だけ repair 再試行する（それでも失敗なら ok=False）。
- 呼び出し回数と時間を計測する（ログには API キー・応募者情報を出さない）。
"""

from __future__ import annotations

import base64
import time
from datetime import date
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from src.phase6.staged_field_pipeline import (
    REPAIR_SUFFIX,
    STORE_PROMPT,
    TOTAL_PROMPT,
    ReadResult,
    parse_json_object,
)
from src.phase6.vision_evidence_client import (
    CropRegion,
    VISION_MODEL,
    regions_for_page,
    render_region_crop,
    run_vision_evidence_pilot_page,
)


class StagedVisionReader:
    def __init__(self, *, client: Anthropic, run_id: str, selected_day: date, output_dir: Path) -> None:
        self.client = client
        self.run_id = run_id
        self.selected_day = selected_day
        self.output_dir = output_dir
        self.calls = {"first_pass": 0, "store_fallback": 0, "total_fallback": 0, "repair_retry": 0}
        self.seconds = {"first_pass": 0.0, "fallback": 0.0}

    # --- crop variants -------------------------------------------------
    @staticmethod
    def _wide(region: CropRegion) -> CropRegion:
        return CropRegion(region.region_id, region.x0_pt - 5, region.y0_pt - 8,
                          region.x1_pt + 5, region.y1_pt + 8)

    def _region(self, page_no: int, region_id: str, variant: str) -> CropRegion:
        base = regions_for_page(page_no, "new")[region_id]
        return base if variant == "A" else self._wide(base)

    # --- Vision call ----------------------------------------------------
    def _ask(self, png: bytes, prompt: str) -> str:
        b64 = base64.b64encode(png).decode()
        msg = self.client.messages.create(
            model=VISION_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": prompt},
            ]}],
        )
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")

    def _read_json(self, png: bytes, prompt: str, counter: str) -> ReadResult:
        self.calls[counter] += 1
        text = self._ask(png, prompt)
        obj = parse_json_object(text)
        if obj is None:
            # 同じ画像で1回だけ format-repair（OCR の再判断ではなく、形式の修復のみ）
            self.calls["repair_retry"] += 1
            text = self._ask(png, prompt + REPAIR_SUFFIX)
            obj = parse_json_object(text)
        if obj is None:
            return ReadResult(ok=False, data={})
        return ReadResult(ok=True, data=obj)

    # --- StagedReader interface -------------------------------------------
    def first_pass(self, page_no: int) -> dict[str, Any]:
        t0 = time.perf_counter()
        self.calls["first_pass"] += 1
        audit = run_vision_evidence_pilot_page(
            self.client,
            run_id=self.run_id,
            pdf_page_no=page_no,
            expected_form_version="new",
            selected_business_date=self.selected_day,
            output_dir=self.output_dir,
        )
        self.seconds["first_pass"] += time.perf_counter() - t0
        pe = audit["page_evidence"]
        sc = pe["store_code_evidence"]
        out: dict[str, Any] = {"store": {"raw": sc.get("raw_value"), "conf": sc.get("confidence")}}
        for name, part in [("intro", "intro_evidence"), ("voice", "voice_evidence")]:
            wt = pe[part]["written_total"]
            out[name] = {"status": wt.get("status"), "value": wt.get("value"), "confidence": wt.get("confidence")}
        return out

    def store_read(self, page_no: int, variant: str) -> ReadResult:
        t0 = time.perf_counter()
        png = render_region_crop(page_no, self._region(page_no, "store_code_region", variant)).image_bytes
        r = self._read_json(png, STORE_PROMPT, "store_fallback")
        self.seconds["fallback"] += time.perf_counter() - t0
        if r.ok:
            prefix = r.data.get("prefix") or ""
            boxes = r.data.get("boxes") or []
            r.data["_raw"] = str(prefix) + "".join(str(b) for b in boxes)
        return r

    def total_read(self, page_no: int, field_name: str, variant: str) -> ReadResult:
        t0 = time.perf_counter()
        png = render_region_crop(page_no, self._region(page_no, field_name, variant)).image_bytes
        r = self._read_json(png, TOTAL_PROMPT, "total_fallback")
        self.seconds["fallback"] += time.perf_counter() - t0
        return r
