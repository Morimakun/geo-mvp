#!/usr/bin/env python3
"""Phase 6: Step 3B v3 監査JSON品質ゲートCLI（読み取り専用）。

責務は既存の監査JSON（src/phase6/vision_evidence_client_v3.py の
run_vision_evidence_pilot_page_v3() が生成したファイル）を読み取り専用で検査する
ことに限定される。監査JSONを書き換えない。Vision APIを呼び出さない。

使用例:
    py -3 scripts/check_phase6_v3_audit.py --audit "<監査JSONのパス>"
    py -3 scripts/check_phase6_v3_audit.py --audit "<監査JSONのパス>" --profile p59

終了コード:
    0: 合格。
    1: 不合格、または監査JSONの読み込み失敗。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.phase6.vision_evidence_quality_gate import (  # noqa: E402
    check_general_quality_gate,
    check_p59_profile,
)

_PROFILE_CHECKS = {"p59": check_p59_profile}


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 6 Step 3B v3監査JSONの品質ゲート検査（読み取り専用。監査JSONは書き換えない）"
    )
    parser.add_argument("--audit", required=True, help="検査対象の監査JSONファイルパス")
    parser.add_argument(
        "--profile",
        choices=sorted(_PROFILE_CHECKS),
        default=None,
        help="一般品質ゲートに加えて検査するページ限定プロフィール（例: p59）",
    )
    args = parser.parse_args(argv)

    audit_path = Path(args.audit)
    print(f"[check_phase6_v3_audit] 対象: {audit_path}")

    if not audit_path.exists():
        print(f"[check_phase6_v3_audit] 監査JSONが見つかりません: {audit_path}", file=sys.stderr)
        return 1
    if not audit_path.is_file():
        print(f"[check_phase6_v3_audit] 通常ファイルではありません: {audit_path}", file=sys.stderr)
        return 1

    try:
        audit_text = audit_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"[check_phase6_v3_audit] 監査JSONを読み込めません: {exc}", file=sys.stderr)
        return 1

    try:
        audit = json.loads(audit_text)
    except json.JSONDecodeError as exc:
        print(f"[check_phase6_v3_audit] 監査JSONをJSONとして解析できません: {exc}", file=sys.stderr)
        return 1

    all_results = list(check_general_quality_gate(audit))
    if args.profile:
        all_results += _PROFILE_CHECKS[args.profile](audit)

    for name, passed, detail in all_results:
        status = "OK" if passed else "NG"
        suffix = f" ({detail})" if detail else ""
        print(f"[check_phase6_v3_audit] {status}: {name}{suffix}")

    overall_ok = bool(all_results) and all(passed for _name, passed, _detail in all_results)
    if overall_ok:
        print("[check_phase6_v3_audit] 合格。")
        return 0

    print("[check_phase6_v3_audit] 不合格。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
