#!/usr/bin/env python3
"""Phase 6: 引継ぎZIP（geo_mvp_handoff.zip等）の読み取り専用プリフライト検査。

設計根拠: Step 3B v3 実家PC作業（2026-07-25/26）事前準備指示。

責務は検査のみに限定される。通常実行ではZIPファイルを展開・コピー・移動・
削除・上書きしない（zipfile.ZipFile.open()/.read()によるメモリ上の読み取りのみで、
ディスクへの書き込みは一切行わない）。

このスクリプトが行わないこと:
    - ZIPの展開・data/phase6_received/等への配置（別途、展開後に人手/別スクリプトで
      ハッシュを再確認しながら行うこと）。
    - Vision API呼び出し・ネットワークアクセス。
    - ANTHROPIC_API_KEYの値の表示（「設定済み」「未設定」のいずれかのみ表示する）。
    - base64・PDF内容・Excel内容・ハッシュ値そのもののログ出力
      （一致/不一致の判定結果と対象の相対パスのみ表示する）。
    - 検査結果ファイルの自動保存（stdout/stderrへの出力のみ）。

安全性検査とファイル同一性照合の区別（重要）:
    危険なパス（絶対パス・ディレクトリトラバーサル等）の判定では、`\\`を`/`へ
    変換してから判定してよい（Windows形式のトラバーサルを見落とさないため）。
    一方、ZIPエントリとSHA256SUMS.txtの記載パスとの同一性照合は、この正規化を
    一切適用せず、記載されたままの文字列で厳密一致のみを行う（basenameだけの
    一致・先頭"./"の自動削除・`\\`から`/`への自動変換によるゆるい一致は行わない）。
    曖昧な表記は「一致」ではなく「失敗」として扱う。

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
# パス安全性（この節のみ、判定目的で`\`を`/`へ変換してよい）
# ============================================================
def _normalize_for_safety_check(name: str) -> str:
    """危険なパスの判定にのみ使う正規化。ファイル同一性照合には使わないこと。"""
    return name.replace("\\", "/")


def _is_absolute_path(name: str) -> bool:
    normalized = _normalize_for_safety_check(name)
    if normalized.startswith("/"):
        return True
    if re.match(r"^[A-Za-z]:/", normalized):  # Windowsドライブレター形式（C:/...）
        return True
    return False


def _has_directory_traversal(name: str) -> bool:
    """パス要素を`/`で分割し、要素が完全に".."であるものだけをディレクトリ
    トラバーサルとして拒否する。

    "report..final.txt"や"version...txt"のように、1つのファイル名の内部に
    連続ドットを含むだけの名前はトラバーサル扱いしない（要素全体が".."と
    完全一致する場合のみを対象とする）。
    """
    normalized = _normalize_for_safety_check(name)
    return any(segment == ".." for segment in normalized.split("/"))


def _find_dangerous_entries(infolist: list) -> list:
    """絶対パス・ディレクトリトラバーサル・重複エントリ名・（Windows上で衝突する）
    大文字小文字違いの同名エントリを検出する。infolistはzipfile.ZipInfoのリスト。

    重複・大小文字衝突の判定は、安全性検査用の正規化（`\\`→`/`）を適用した文字列
    同士で行う（実在するファイルシステム上での衝突可能性を検出する目的のため）。
    これはファイル同一性照合（SHA256SUMS.txtとの照合）には使わない。
    """
    dangerous = []
    seen_normalized: dict = {}  # 正規化名 -> 元のエントリ名（重複検出用）
    seen_casefold: dict = {}  # casefold後の正規化名 -> 正規化名（大小文字衝突検出用）

    for info in infolist:
        name = info.filename
        if _is_absolute_path(name):
            dangerous.append((name, "absolute_path"))
            continue
        if _has_directory_traversal(name):
            dangerous.append((name, "directory_traversal"))
            continue

        normalized = _normalize_for_safety_check(name)

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
# SHA256SUMS.txt の解析（ファイル同一性照合。正規化を一切適用しない）
# ============================================================
def _parse_sha256sums(text: str) -> dict:
    """SHA256SUMS.txtの内容を解析し、{記載された通りのパス: 小文字16進ハッシュ} を返す。

    パスは記載された文字列をそのまま同一性照合のキーとして使う
    （basenameへの単純化・先頭"./"の自動削除・`\\`から`/`への自動変換は一切行わない。
    曖昧な表記はここでは「補正」せず、後段の照合で単に一致しない＝失敗として扱われる）。

    空行（空白のみの行を含む）以外で解析できない行が1つでもあればHandoffCheckErrorを
    送出する（コメント行という特別扱いはしない）。
    同一パスが複数回記載されている場合は、ハッシュ値が同一であっても曖昧として失敗にする。
    casefold後に衝突する複数の異なるパスが記載されている場合も曖昧として失敗にする。
    """
    result: dict = {}
    seen_casefold: dict = {}  # casefold後のパス -> 記載されたままのパス（衝突検出用）

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
        path = m.group(3)  # 記載されたまま。正規化・補正は一切行わない。

        if path in result:
            raise HandoffCheckError(
                f"SHA256SUMS.txt: パス{path!r}が複数行に記載されています"
                "（ハッシュ値が同一であっても曖昧なため許可しません）"
            )
        folded = path.casefold()
        if folded in seen_casefold and seen_casefold[folded] != path:
            raise HandoffCheckError(
                f"SHA256SUMS.txt: パス{path!r}と{seen_casefold[folded]!r}が"
                "大文字小文字の違いを除いて衝突しています"
            )
        seen_casefold[folded] = path
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
# マニフェスト全体の検証（Part B: 対象PDFだけでなく全通常ファイル）
# ============================================================
def _verify_all_manifest_files(
    zf: zipfile.ZipFile,
    manifest: dict,
    file_infos: list,
) -> dict:
    """SHA256SUMS.txt記載の全ファイルと、ZIP内の全通常ファイルを突き合わせて検証する。

    Returns:
        {
            "raw_names": set,               # ZIP内の通常ファイルの実際のエントリ名集合
            "total": int,                    # マニフェスト記載件数
            "match_paths": list,             # 実測値がマニフェストと一致したパス
            "mismatch_paths": list,          # 実測値がマニフェストと不一致だったパス
            "missing_paths": list,           # マニフェストに記載があるがZIP内に見つからないパス
            "unlisted_paths": list,          # ZIP内にあるがマニフェストに記載がないパス
                                              # （SHA256SUMS.txt自身は対象外）
        }

    厳密な同一性照合のみを行う（basename一致・パス正規化による緩和は行わない）。
    ディレクトリエントリはfile_infosの時点で既に除外されている前提。
    """
    raw_names = {info.filename for info in file_infos}

    match_paths: list = []
    mismatch_paths: list = []
    missing_paths: list = []

    for path in sorted(manifest.keys()):
        if path not in raw_names:
            missing_paths.append(path)
            continue
        expected_digest = manifest[path]
        actual_digest = _stream_sha256_of_entry(zf, path)
        if actual_digest == expected_digest:
            match_paths.append(path)
        else:
            mismatch_paths.append(path)

    manifest_paths = set(manifest.keys())
    unlisted_paths = sorted(
        info.filename
        for info in file_infos
        if info.filename != REQUIRED_SHA256SUMS and info.filename not in manifest_paths
    )

    return {
        "raw_names": raw_names,
        "total": len(manifest),
        "match_paths": match_paths,
        "mismatch_paths": mismatch_paths,
        "missing_paths": missing_paths,
        "unlisted_paths": unlisted_paths,
    }


# ============================================================
# 検査本体
# ============================================================
def check_handoff_zip(zip_path: Path, *, expected_pdf_sha256: str = EXPECTED_PDF_SHA256) -> list:
    """検査を実行し、[(check_name, passed, detail), ...] を返す（常に返す。例外を投げない）。

    危険なZIPパスが見つかった場合はそこで処理を止める。それ以外は、途中で
    個々のファイルが1件失敗しても、安全に検証可能な残りの項目は検証を続け、
    結果を集約して返す。

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

        # ファイル同一性照合は、記載されたままのエントリ名（正規化なし）の厳密一致のみで行う。
        raw_names = {info.filename for info in file_infos}

        readme_present = REQUIRED_README in raw_names
        add("readme_exists", readme_present, "" if readme_present else f"{REQUIRED_README}が見つかりません")

        sha256sums_present = REQUIRED_SHA256SUMS in raw_names
        add(
            "sha256sums_exists",
            sha256sums_present,
            "" if sha256sums_present else f"{REQUIRED_SHA256SUMS}が見つかりません",
        )

        pdf_entry_present = TARGET_PDF_ENTRY in raw_names
        add(
            "target_pdf_entry_exists",
            pdf_entry_present,
            "" if pdf_entry_present else f"{TARGET_PDF_ENTRY}が見つかりません",
        )

        if not sha256sums_present:
            return results  # SHA256SUMS.txt自体がなければ以降のハッシュ検証は行えない

        try:
            sha256sums_text = zf.read(REQUIRED_SHA256SUMS).decode("utf-8", errors="strict")
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

        # ここから先は、個別ファイルが1件失敗しても残りの検証を続け、結果を集約する。
        verification = _verify_all_manifest_files(zf, manifest, file_infos)

        add(
            "manifest_verification_summary",
            True,
            (
                f"検証対象{verification['total']}件 "
                f"一致{len(verification['match_paths'])}件 "
                f"不一致{len(verification['mismatch_paths'])}件 "
                f"欠落{len(verification['missing_paths'])}件 "
                f"未記載{len(verification['unlisted_paths'])}件"
            ),
        )
        add(
            "manifest_files_present",
            not verification["missing_paths"],
            f"欠落: {verification['missing_paths']}" if verification["missing_paths"] else "",
        )
        add(
            "manifest_files_match",
            not verification["mismatch_paths"],
            f"不一致: {verification['mismatch_paths']}" if verification["mismatch_paths"] else "",
        )
        add(
            "zip_files_all_listed_in_manifest",
            not verification["unlisted_paths"],
            f"未記載: {verification['unlisted_paths']}" if verification["unlisted_paths"] else "",
        )

        if pdf_entry_present and manifest_has_target and TARGET_PDF_ENTRY not in verification["missing_paths"]:
            actual_pdf_digest = _stream_sha256_of_entry(zf, TARGET_PDF_ENTRY)
            matches_expected = actual_pdf_digest == expected_pdf_sha256
            add(
                "target_pdf_matches_expected",
                matches_expected,
                "" if matches_expected else "実ファイルのSHA-256が期待値と一致しません",
            )
        else:
            add(
                "target_pdf_matches_expected",
                False,
                "対象PDFが未検証のため期待値との一致を確認できません",
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
