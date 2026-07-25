#!/usr/bin/env python3
"""Phase 6: 引継ぎZIP（geo_mvp_handoff.zip等）の読み取り専用プリフライト検査。

設計根拠: Step 3B v3 実家PC作業（2026-07-25）事前準備指示。

責務は検査のみに限定される。通常実行ではZIPファイルを展開・コピー・移動・
削除・上書きしない（zipfile.ZipFile.open()/.read()によるメモリ上の読み取りのみで、
ディスクへの書き込みは一切行わない）。

このスクリプトが行わないこと:
    - ZIPの展開・data/phase6_received/等への配置（別途、展開後に人手/別スクリプトで
      ハッシュを再確認しながら行うこと）。
    - Vision API呼び出し・ネットワークアクセス。
    - ANTHROPIC_API_KEYの値の表示（「設定済み」「未設定」のいずれかのみ表示する）。
    - base64・PDF内容・Excel内容のログ出力。
    - 検査結果ファイルの自動保存（stdout/stderrへの出力のみ）。

使用例:
    py -3 scripts/check_phase6_handoff.py --zip "C:\\Users\\maris\\Desktop\\geo_mvp_handoff.zip"

終了コード:
    0: 全検査に合格。
    1: 検査失敗（不足・破損・ハッシュ不一致・危険なパス等）。理由はstdout/stderrに出力する。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Optional

REQUIRED_README = "README.md"
REQUIRED_SHA256SUMS = "SHA256SUMS.txt"
TARGET_PDF_ENTRY = "data/phase6_received/SFA用紙.pdf"
EXPECTED_PDF_SHA256 = "a744a398f5262ba31e5220721014358f9c236d718e01ac492b796b18dc0ed174"

_CHUNK_SIZE = 1 << 20  # 1MB単位でストリーム読み取りする（展開せず、全体をメモリへ載せない）

# sha256sumコマンド標準の書式（1行）: "<64桁16進数>  <パス>"（テキストモード）
# または "<64桁16進数> *<パス>"（バイナリモード）。それ以外の書式は解析エラーとする。
_SHA256SUMS_LINE_RE = re.compile(r"^([0-9a-fA-F]{64})[ \t]+(\*)?(.+)$")


class HandoffCheckError(Exception):
    """検査を続行できない異常（理由はstr(exc)に格納）。"""


# ============================================================
# パス安全性
# ============================================================
def _normalize_entry_name(name: str) -> str:
    return name.replace("\\", "/")


def _is_absolute_path(name: str) -> bool:
    normalized = _normalize_entry_name(name)
    if normalized.startswith("/"):
        return True
    if re.match(r"^[A-Za-z]:/", normalized):  # Windowsドライブレター形式（C:/...）
        return True
    return False


def _has_directory_traversal(name: str) -> bool:
    """正規化後のパスに連続する2つ以上のドット（".."）が含まれていれば拒否する。

    ".."との完全一致セグメントだけを見ると、"safe....\\evil"のような
    「4つのドットが1セグメントの中に紛れ込んでいる」形を見落とす。連続ドットの
    出現そのものを禁止することで、想定される正規のファイル名（README.md・
    SHA256SUMS.txt・SFA用紙.pdf・SFAエクスポートマスター*.xlsx等）には一切影響を
    与えず、"..""や"...."等のあらゆる連続ドットパターンを安全側で一律拒否する。
    """
    normalized = _normalize_entry_name(name)
    return ".." in normalized


def _find_dangerous_entries(infolist: list) -> list:
    """絶対パス・ディレクトリトラバーサル・重複エントリ名・（Windows上で衝突する）
    大文字小文字違いの同名エントリを検出する。infolistはzipfile.ZipInfoのリスト。"""
    dangerous = []
    seen_normalized: dict = {}  # 正規化名 -> 元のエントリ名（重複検出用）
    seen_casefold: dict = {}  # casefold後の正規化名 -> 元のエントリ名（大小文字衝突検出用）

    for info in infolist:
        name = info.filename
        if _is_absolute_path(name):
            dangerous.append((name, "absolute_path"))
            continue
        if _has_directory_traversal(name):
            dangerous.append((name, "directory_traversal"))
            continue

        normalized = _normalize_entry_name(name)

        if normalized in seen_normalized:
            dangerous.append((name, "duplicate_entry_name"))
            continue
        seen_normalized[normalized] = name

        folded = normalized.casefold()
        if folded in seen_casefold and seen_casefold[folded] != normalized:
            dangerous.append((name, "case_insensitive_collision"))
            continue
        seen_casefold[folded] = normalized

    return dangerous


# ============================================================
# SHA256SUMS.txt の解析
# ============================================================
def _parse_sha256sums(text: str) -> dict:
    """SHA256SUMS.txtの内容を解析し、{正規化パス: 小文字16進ハッシュ} を返す。

    空行（空白のみの行を含む）以外で解析できない行が1つでもあればHandoffCheckErrorを
    送出する（コメント行という特別扱いはしない。書式に差があっても無条件に推測で
    一致扱いしない。曖昧な行は失敗として扱う）。
    同一パスに異なるハッシュ値が複数記載されている場合も曖昧として失敗にする。
    """
    result: dict = {}
    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip("\r")
        if not line.strip():
            continue  # 空行（空白のみの行を含む）だけを許容し、それ以外は必ず書式検証する
        m = _SHA256SUMS_LINE_RE.match(line)
        if not m:
            raise HandoffCheckError(
                f"SHA256SUMS.txt: {line_no}行目の書式を解析できません"
                "（想定書式: '<64桁16進数の空白区切り> <ファイルパス>'）"
            )
        digest = m.group(1).lower()
        path = _normalize_entry_name(m.group(3).strip())
        if path.startswith("./"):
            path = path[2:]
        if path in result and result[path] != digest:
            raise HandoffCheckError(
                f"SHA256SUMS.txt: パス{path!r}に対して異なるハッシュ値が複数行に記載されており曖昧です"
            )
        result[path] = digest
    return result


def _stream_sha256_of_entry(zf: zipfile.ZipFile, entry_name: str) -> str:
    """ZIPエントリをディスクへ展開せず、ストリームで読みながらSHA-256を計算する。"""
    hasher = hashlib.sha256()
    with zf.open(entry_name, "r") as f:
        while True:
            chunk = f.read(_CHUNK_SIZE)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


# ============================================================
# 検査本体
# ============================================================
def check_handoff_zip(zip_path: Path, *, expected_pdf_sha256: str = EXPECTED_PDF_SHA256) -> list:
    """検査を実行し、[(check_name, passed, detail), ...] を返す（常に返す。例外を投げない）。
    途中で継続不能な異常（ZIPが開けない等）があれば、そこまでの結果を返す。

    expected_pdf_sha256はテスト用の差し替えポイント（デフォルトは実PDFの期待値定数）。
    合成ZIPでは実PDFと同一のSHA-256を再現することはできない（SHA-256の原像計算に相当し
    現実的に不可能なため）。CLI（main()）からは常にデフォルト値（実PDFの期待値）を使う。
    """
    results: list = []

    def add(name: str, passed: bool, detail: str = "") -> bool:
        results.append((name, passed, detail))
        return passed

    zip_exists = zip_path.exists()
    if not add("zip_exists", zip_exists, "" if zip_exists else f"ファイルが存在しません: {zip_path}"):
        return results

    is_regular = zip_path.is_file()
    if not add("zip_is_regular_file", is_regular, "" if is_regular else f"通常ファイルではありません: {zip_path}"):
        return results

    try:
        zf = zipfile.ZipFile(zip_path, "r")
    except zipfile.BadZipFile as exc:
        add("zip_can_open", False, f"ZIPとして開けません: {exc}")
        return results
    add("zip_can_open", True)

    with zf:
        infolist = zf.infolist()

        dangerous = _find_dangerous_entries(infolist)
        if not add(
            "zip_no_dangerous_paths",
            not dangerous,
            f"危険なパスを含みます: {[(n, reason) for n, reason in dangerous]}" if dangerous else "",
        ):
            return results  # 危険なパスがある場合はこれ以上読み取らない

        # ディレクトリエントリ（ZipInfo.is_dir()）は必須ファイルとして数えない・照合しない。
        file_infos = [info for info in infolist if not info.is_dir()]
        add("zip_file_count", True, f"{len(file_infos)}件")

        normalized_to_original = {
            _normalize_entry_name(info.filename): info.filename for info in file_infos
        }

        readme_present = REQUIRED_README in normalized_to_original
        add("readme_exists", readme_present, "" if readme_present else f"{REQUIRED_README}が見つかりません")

        sha256sums_present = REQUIRED_SHA256SUMS in normalized_to_original
        add(
            "sha256sums_exists",
            sha256sums_present,
            "" if sha256sums_present else f"{REQUIRED_SHA256SUMS}が見つかりません",
        )

        pdf_entry_present = TARGET_PDF_ENTRY in normalized_to_original
        add(
            "target_pdf_entry_exists",
            pdf_entry_present,
            "" if pdf_entry_present else f"{TARGET_PDF_ENTRY}が見つかりません",
        )

        if not sha256sums_present:
            return results  # SHA256SUMS.txt自体がなければ以降のハッシュ検証は行えない

        try:
            sha256sums_text = zf.read(normalized_to_original[REQUIRED_SHA256SUMS]).decode(
                "utf-8", errors="strict"
            )
        except UnicodeDecodeError as exc:
            add("sha256sums_parseable", False, f"UTF-8として読み取れません: {exc}")
            return results

        try:
            manifest = _parse_sha256sums(sha256sums_text)
        except HandoffCheckError as exc:
            add("sha256sums_parseable", False, str(exc))
            return results
        add("sha256sums_parseable", True, f"{len(manifest)}エントリ")

        manifest_has_target = TARGET_PDF_ENTRY in manifest
        add(
            "sha256sums_has_target_pdf_entry",
            manifest_has_target,
            "" if manifest_has_target else f"SHA256SUMS.txtに{TARGET_PDF_ENTRY}の記載が見つかりません",
        )

        if not (pdf_entry_present and manifest_has_target):
            return results  # 実体・記載のいずれかが欠けていればハッシュ比較は行えない

        manifest_digest = manifest[TARGET_PDF_ENTRY]
        actual_digest = _stream_sha256_of_entry(zf, normalized_to_original[TARGET_PDF_ENTRY])

        matches_manifest = actual_digest == manifest_digest
        add(
            "target_pdf_matches_manifest",
            matches_manifest,
            "" if matches_manifest else "実ファイルのSHA-256とSHA256SUMS.txtの記載が一致しません",
        )

        matches_expected = actual_digest == expected_pdf_sha256
        add(
            "target_pdf_matches_expected",
            matches_expected,
            "" if matches_expected else "実ファイルのSHA-256が期待値と一致しません",
        )

    return results


def _api_key_status() -> str:
    return "設定済み" if os.environ.get("ANTHROPIC_API_KEY") else "未設定"


def main(argv: Optional[list] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase 6引継ぎZIPの読み取り専用プリフライト検査（展開・配置は行わない）"
    )
    parser.add_argument("--zip", required=True, help="検査対象のZIPファイルパス")
    args = parser.parse_args(argv)

    zip_path = Path(args.zip)

    print(f"[check_phase6_handoff] 対象ZIP: {zip_path}")
    print(f"[check_phase6_handoff] ANTHROPIC_API_KEY: {_api_key_status()}")

    results = check_handoff_zip(zip_path)

    for name, passed, detail in results:
        status = "OK" if passed else "NG"
        suffix = f" ({detail})" if detail else ""
        print(f"[check_phase6_handoff] {status}: {name}{suffix}")

    overall_ok = bool(results) and all(passed for _name, passed, _detail in results)
    if overall_ok:
        print("[check_phase6_handoff] 全検査に合格しました。")
        return 0

    print("[check_phase6_handoff] 検査に失敗しました。配置作業を行わないでください。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
