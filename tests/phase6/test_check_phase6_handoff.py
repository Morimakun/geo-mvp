"""scripts/check_phase6_handoff.py のテスト。

実データ（実PDF・実Excel・実APIキー）は一切使用しない。すべてtmp_pathへ生成した
合成ZIPのみでテストする。環境変数のテスト用値も"dummy-secret-value"のような
明確なダミー値のみを使用し、実際のAPIキー・個人情報は含めない。
"""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from scripts.check_phase6_handoff import (  # noqa: E402
    EXPECTED_PDF_SHA256,
    REQUIRED_README,
    REQUIRED_SHA256SUMS,
    TARGET_PDF_ENTRY,
    _detect_single_wrapper_prefix,
    _find_duplicate_or_casefold_collisions,
    check_handoff_zip,
    main,
)

_SYNTHETIC_PDF_BYTES = b"%SYNTHETIC-PLACEHOLDER-NOT-A-REAL-PDF%" * 100
_DUMMY_README_TEXT = "# synthetic handoff fixture for tests\n"


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_zip(
    tmp_path: Path,
    *,
    name: str = "handoff.zip",
    entries: dict,
) -> Path:
    """entries: {zipエントリ名: bytes|str} からZIPファイルをtmp_pathへ生成する。"""
    zip_path = tmp_path / name
    with zipfile.ZipFile(zip_path, "w") as zf:
        for entry_name, data in entries.items():
            zf.writestr(entry_name, data)
    return zip_path


def _readme_digest() -> str:
    return _sha256_hex(_DUMMY_README_TEXT.encode("utf-8"))


def _valid_entries(*, pdf_bytes: bytes = _SYNTHETIC_PDF_BYTES) -> dict:
    """README.md・SHA256SUMS.txt・対象PDFの3ファイルが揃った、完全に整合する
    合成ZIPの中身。SHA256SUMS.txtにはREADME.md・対象PDFの両方を記載する
    （SHA256SUMS.txt自身は記載不要）。"""
    pdf_digest = _sha256_hex(pdf_bytes)
    sha256sums = f"{_readme_digest()}  {REQUIRED_README}\n{pdf_digest}  {TARGET_PDF_ENTRY}\n"
    return {
        REQUIRED_README: _DUMMY_README_TEXT,
        REQUIRED_SHA256SUMS: sha256sums,
        TARGET_PDF_ENTRY: pdf_bytes,
    }


def _results_dict(results: list) -> dict:
    return {name: passed for name, passed, _detail in results}


def _results_detail(results: list, name: str) -> str:
    for n, _passed, detail in results:
        if n == name:
            return detail
    raise KeyError(name)


# ============================================================
# 正常系
# ============================================================
class TestValidSyntheticZip:
    def test_all_checks_pass_when_hash_matches_synthetic_expected_value(self, tmp_path):
        zip_path = _build_zip(tmp_path, entries=_valid_entries())
        synthetic_expected = _sha256_hex(_SYNTHETIC_PDF_BYTES)

        results = check_handoff_zip(zip_path, expected_pdf_sha256=synthetic_expected)

        assert results, "結果が空であってはならない"
        assert all(passed for _name, passed, _detail in results)

    def test_file_count_is_reported(self, tmp_path):
        zip_path = _build_zip(tmp_path, entries=_valid_entries())
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        file_count_entries = [d for n, _p, d in results if n == "zip_file_count"]
        assert file_count_entries == ["3件"]

    def test_manifest_verification_summary_counts(self, tmp_path):
        zip_path = _build_zip(tmp_path, entries=_valid_entries())
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        summary = _results_detail(results, "manifest_verification_summary")
        assert "検証対象2件" in summary
        assert "一致2件" in summary
        assert "不一致0件" in summary
        assert "欠落0件" in summary
        assert "未記載0件" in summary

    def test_sha256sums_self_listing_is_not_required_for_success(self, tmp_path):
        # SHA256SUMS.txt自身がマニフェストに記載されていなくても成功できること。
        entries = _valid_entries()
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        d = _results_dict(results)
        assert d["zip_files_all_listed_in_manifest"] is True
        assert all(passed for _n, passed, _d in results)

    def test_main_runs_cleanly_against_valid_zip_using_real_pdf_constant(self, tmp_path, monkeypatch, capsys):
        # main()は常にEXPECTED_PDF_SHA256（実PDF用の定数）を使うため、合成ZIPでは
        # target_pdf_matches_expectedだけが意図的に不一致になり、終了コードは1になる。
        zip_path = _build_zip(tmp_path, entries=_valid_entries())
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        exit_code = main(["--zip", str(zip_path)])
        captured = capsys.readouterr()
        assert exit_code == 1  # EXPECTED_PDF_SHA256（実PDF）とは一致しないため
        assert "OK: manifest_files_match" in captured.out
        assert "NG: target_pdf_matches_expected" in captured.out
        assert "未設定" in captured.out


# ============================================================
# 異常系: 欠損・破損
# ============================================================
class TestMissingOrCorrupt:
    def test_zip_does_not_exist(self, tmp_path):
        missing = tmp_path / "does_not_exist.zip"
        results = check_handoff_zip(missing)
        assert _results_dict(results) == {"zip_exists": False}

    def test_zip_path_is_a_directory_not_a_file(self, tmp_path):
        directory = tmp_path / "not_a_zip"
        directory.mkdir()
        results = check_handoff_zip(directory)
        d = _results_dict(results)
        assert d["zip_exists"] is True
        assert d["zip_is_regular_file"] is False

    def test_corrupt_zip_fails_to_open(self, tmp_path):
        corrupt = tmp_path / "corrupt.zip"
        corrupt.write_bytes(b"this is not a valid zip file at all")
        results = check_handoff_zip(corrupt)
        d = _results_dict(results)
        assert d["zip_can_open"] is False

    def test_readme_missing(self, tmp_path):
        entries = _valid_entries()
        del entries[REQUIRED_README]
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["readme_exists"] is False

    def test_sha256sums_missing(self, tmp_path):
        entries = _valid_entries()
        del entries[REQUIRED_SHA256SUMS]
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["sha256sums_exists"] is False
        assert "sha256sums_parseable" not in d  # SHA256SUMS.txtがなければ以降の検査は行わない

    def test_target_pdf_missing(self, tmp_path):
        entries = _valid_entries()
        del entries[TARGET_PDF_ENTRY]
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["target_pdf_entry_exists"] is False
        assert d["manifest_files_present"] is False  # マニフェストには記載があるが実体がない


# ============================================================
# 異常系: ハッシュ不一致・書式異常
# ============================================================
class TestHashAndFormatFailures:
    def test_target_pdf_hash_mismatch_against_real_expected_constant(self, tmp_path):
        # 合成PDFのハッシュは、実PDFのEXPECTED_PDF_SHA256とは一致しないはず
        # （合成データのみでの検証。実PDFバイト列は一切使用していない）。
        zip_path = _build_zip(tmp_path, entries=_valid_entries())
        results = check_handoff_zip(zip_path, expected_pdf_sha256=EXPECTED_PDF_SHA256)
        d = _results_dict(results)
        assert d["manifest_files_match"] is True  # 実体とSHA256SUMS.txtの記載は一致
        assert d["target_pdf_matches_expected"] is False  # 実PDF用の期待値とは一致しない

    def test_target_pdf_hash_mismatch_against_manifest(self, tmp_path):
        pdf_bytes = _SYNTHETIC_PDF_BYTES
        wrong_digest = _sha256_hex(b"different content entirely")
        entries = {
            REQUIRED_README: _DUMMY_README_TEXT,
            REQUIRED_SHA256SUMS: (
                f"{_readme_digest()}  {REQUIRED_README}\n{wrong_digest}  {TARGET_PDF_ENTRY}\n"
            ),
            TARGET_PDF_ENTRY: pdf_bytes,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(pdf_bytes))
        d = _results_dict(results)
        assert d["manifest_files_match"] is False
        assert TARGET_PDF_ENTRY in _results_detail(results, "manifest_files_match")

    def test_sha256sums_basename_only_entry_does_not_match_target_path(self, tmp_path):
        # SHA256SUMS.txtに basename（"SFA用紙.pdf"）だけが記載されていても、
        # data/phase6_received/SFA用紙.pdf への記載として推測で一致扱いしないこと。
        digest = _sha256_hex(_SYNTHETIC_PDF_BYTES)
        entries = {
            REQUIRED_README: _DUMMY_README_TEXT,
            REQUIRED_SHA256SUMS: f"{_readme_digest()}  {REQUIRED_README}\n{digest}  SFA用紙.pdf\n",
            TARGET_PDF_ENTRY: _SYNTHETIC_PDF_BYTES,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["sha256sums_parseable"] is True
        assert d["sha256sums_has_target_pdf_entry"] is False

    def test_sha256sums_leading_dot_slash_is_not_auto_stripped(self, tmp_path):
        # SHA256SUMS.txtに "./data/phase6_received/SFA用紙.pdf" と記載されていても、
        # 先頭の"./"を自動削除して一致扱いしない（曖昧な表記は失敗として報告する）。
        digest = _sha256_hex(_SYNTHETIC_PDF_BYTES)
        entries = {
            REQUIRED_README: _DUMMY_README_TEXT,
            REQUIRED_SHA256SUMS: f"{_readme_digest()}  {REQUIRED_README}\n{digest}  ./{TARGET_PDF_ENTRY}\n",
            TARGET_PDF_ENTRY: _SYNTHETIC_PDF_BYTES,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["sha256sums_has_target_pdf_entry"] is False
        assert d["zip_files_all_listed_in_manifest"] is False  # 実体側は"未記載"扱いになる

    def test_sha256sums_backslash_path_is_not_auto_converted(self, tmp_path):
        # SHA256SUMS.txtに"data\phase6_received\SFA用紙.pdf"（バックスラッシュ）と
        # 記載されていても、実際のZIPエントリ（フォワードスラッシュ）と自動変換して
        # 一致扱いしない。
        digest = _sha256_hex(_SYNTHETIC_PDF_BYTES)
        backslash_path = "data\\phase6_received\\SFA用紙.pdf"
        entries = {
            REQUIRED_README: _DUMMY_README_TEXT,
            REQUIRED_SHA256SUMS: f"{_readme_digest()}  {REQUIRED_README}\n{digest}  {backslash_path}\n",
            TARGET_PDF_ENTRY: _SYNTHETIC_PDF_BYTES,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["sha256sums_has_target_pdf_entry"] is False

    def test_sha256sums_hash_like_comment_line_is_not_silently_ignored(self, tmp_path):
        # "#"始まりの行を特別扱い（コメントとしてスキップ）しないこと。
        # 空行以外の不正行は必ず解析エラーとして報告する。
        digest = _sha256_hex(_SYNTHETIC_PDF_BYTES)
        entries = {
            REQUIRED_README: _DUMMY_README_TEXT,
            REQUIRED_SHA256SUMS: f"# this looks like a comment\n{digest}  {TARGET_PDF_ENTRY}\n",
            TARGET_PDF_ENTRY: _SYNTHETIC_PDF_BYTES,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["sha256sums_parseable"] is False

    def test_sha256sums_malformed_line(self, tmp_path):
        entries = {
            REQUIRED_README: _DUMMY_README_TEXT,
            REQUIRED_SHA256SUMS: "not-a-valid-sha256sums-line at all\n",
            TARGET_PDF_ENTRY: _SYNTHETIC_PDF_BYTES,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["sha256sums_parseable"] is False

    def test_sha256sums_duplicate_path_same_hash_is_rejected(self, tmp_path):
        # ハッシュ値が同一であっても、同一パスが2回記載されていれば曖昧として失敗する。
        digest = _sha256_hex(_SYNTHETIC_PDF_BYTES)
        entries = {
            REQUIRED_README: _DUMMY_README_TEXT,
            REQUIRED_SHA256SUMS: (
                f"{_readme_digest()}  {REQUIRED_README}\n"
                f"{digest}  {TARGET_PDF_ENTRY}\n"
                f"{digest}  {TARGET_PDF_ENTRY}\n"
            ),
            TARGET_PDF_ENTRY: _SYNTHETIC_PDF_BYTES,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["sha256sums_parseable"] is False

    def test_sha256sums_ambiguous_conflicting_hashes_for_same_path(self, tmp_path):
        digest_a = _sha256_hex(b"a")
        digest_b = _sha256_hex(b"b")
        entries = {
            REQUIRED_README: _DUMMY_README_TEXT,
            REQUIRED_SHA256SUMS: f"{digest_a}  {TARGET_PDF_ENTRY}\n{digest_b}  {TARGET_PDF_ENTRY}\n",
            TARGET_PDF_ENTRY: _SYNTHETIC_PDF_BYTES,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["sha256sums_parseable"] is False

    def test_sha256sums_casefold_collision_between_different_paths_is_rejected(self, tmp_path):
        digest = _sha256_hex(_SYNTHETIC_PDF_BYTES)
        entries = {
            REQUIRED_README: _DUMMY_README_TEXT,
            REQUIRED_SHA256SUMS: (
                f"{_readme_digest()}  {REQUIRED_README}\n"
                f"{digest}  {TARGET_PDF_ENTRY}\n"
                f"{digest}  {TARGET_PDF_ENTRY.upper()}\n"
            ),
            TARGET_PDF_ENTRY: _SYNTHETIC_PDF_BYTES,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["sha256sums_parseable"] is False


# ============================================================
# Part B: マニフェスト全体の検証（対象PDF以外のファイルも含む）
# ============================================================
class TestManifestWideVerification:
    def test_extra_zip_file_not_listed_in_manifest_is_rejected(self, tmp_path):
        entries = _valid_entries()
        entries["data/phase6_received/SFAエクスポートマスター0625nn.xlsx"] = b"synthetic excel placeholder"
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        d = _results_dict(results)
        assert d["zip_files_all_listed_in_manifest"] is False
        assert "SFAエクスポートマスター0625nn.xlsx" in _results_detail(results, "zip_files_all_listed_in_manifest")

    def test_manifest_listed_extra_file_is_verified_too(self, tmp_path):
        entries = _valid_entries()
        extra_bytes = b"synthetic excel placeholder"
        extra_path = "data/phase6_received/SFAエクスポートマスター0625nn.xlsx"
        entries[extra_path] = extra_bytes
        pdf_digest = _sha256_hex(_SYNTHETIC_PDF_BYTES)
        entries[REQUIRED_SHA256SUMS] = (
            f"{_readme_digest()}  {REQUIRED_README}\n"
            f"{pdf_digest}  {TARGET_PDF_ENTRY}\n"
            f"{_sha256_hex(extra_bytes)}  {extra_path}\n"
        )
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path, expected_pdf_sha256=pdf_digest)
        d = _results_dict(results)
        assert d["zip_files_all_listed_in_manifest"] is True
        assert d["manifest_files_match"] is True
        summary = _results_detail(results, "manifest_verification_summary")
        assert "検証対象3件" in summary
        assert "一致3件" in summary

    def test_directory_entries_are_excluded_from_counts(self, tmp_path):
        zip_path = tmp_path / "with_dir.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("data/phase6_received/", "")  # ディレクトリエントリ
            for entry_name, data in _valid_entries().items():
                zf.writestr(entry_name, data)

        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        d = _results_dict(results)
        file_count_entries = [detail for n, _p, detail in results if n == "zip_file_count"]
        assert file_count_entries == ["3件"]  # ディレクトリエントリは数えない
        assert d["zip_files_all_listed_in_manifest"] is True


# ============================================================
# 異常系: 危険なパス（Part A: 要素完全一致による判定）
# ============================================================
class TestDangerousPaths:
    def test_absolute_path_entry_is_rejected(self, tmp_path):
        entries = _valid_entries()
        entries["/etc/passwd"] = b"malicious"
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["zip_no_dangerous_paths"] is False
        # 危険なパスが見つかった時点でそれ以降の検査は行わない。
        assert "readme_exists" not in d

    def test_windows_drive_absolute_path_entry_is_rejected(self, tmp_path):
        entries = _valid_entries()
        entries["C:/Windows/System32/evil.dll"] = b"malicious"
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["zip_no_dangerous_paths"] is False

    @pytest.mark.parametrize(
        "dangerous_entry",
        [
            "/absolute/path",
            "\\absolute\\path",
            "C:\\absolute\\path",
            "C:/absolute/path",
            "../evil",
            "..\\evil",
            "safe/../../evil",
            "safe\\..\\..\\evil",
            "safe/..\\evil",  # スラッシュとバックスラッシュを混在させた親ディレクトリ参照
            "safe\\../evil",
        ],
    )
    def test_each_required_dangerous_pattern_is_rejected(self, tmp_path, dangerous_entry):
        entries = _valid_entries()
        entries[dangerous_entry] = b"malicious"
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["zip_no_dangerous_paths"] is False

    @pytest.mark.parametrize("benign_entry", ["report..final.txt", "version...txt", "safe....txt"])
    def test_filenames_with_internal_consecutive_dots_are_not_traversal(self, tmp_path, benign_entry):
        # ファイル名内部に連続ドットを含むだけの名前は、要素全体が".."と完全一致しない限り
        # トラバーサル扱いしない。（マニフェストに未記載のため他のチェックは落ちてよいが、
        # zip_no_dangerous_pathsだけはTrueのままであることを確認する。）
        entries = _valid_entries()
        entries[benign_entry] = b"benign content"
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["zip_no_dangerous_paths"] is True

    def test_duplicate_entry_name_is_rejected(self, tmp_path):
        # zipfileは同名エントリの重複書き込みを禁止しないため、意図的に低レベルAPIで作成する。
        zip_path = tmp_path / "dup.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            for entry_name, data in _valid_entries().items():
                zf.writestr(entry_name, data)
            zf.writestr(TARGET_PDF_ENTRY, b"a second, different payload for the same name")

        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["zip_no_dangerous_paths"] is False

    def test_case_insensitive_collision_is_rejected(self, tmp_path):
        entries = _valid_entries()
        entries[TARGET_PDF_ENTRY.upper()] = b"same logical path, different case"
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["zip_no_dangerous_paths"] is False

    def test_directory_entry_is_not_mistaken_for_required_file(self, tmp_path):
        # ディレクトリエントリ名がたまたま必須ファイル名と同じでも、ファイルとして
        # 誤認してはならない（ZipInfo.is_dir()で正しく除外されること）。
        zip_path = tmp_path / "dir_confusion.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(f"{REQUIRED_README}/", "")  # ディレクトリエントリ（末尾スラッシュ）
            for entry_name, data in _valid_entries().items():
                if entry_name != REQUIRED_README:
                    zf.writestr(entry_name, data)

        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["readme_exists"] is False  # ディレクトリはファイルとして扱わない


# ============================================================
# ANTHROPIC_API_KEYの値が出力へ漏れないこと
# ============================================================
class TestApiKeyNeverLeaked:
    def test_api_key_value_never_appears_in_stdout(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-secret-value")
        zip_path = _build_zip(tmp_path, entries=_valid_entries())

        main(["--zip", str(zip_path)])

        captured = capsys.readouterr()
        assert "dummy-secret-value" not in captured.out
        assert "dummy-secret-value" not in captured.err
        assert "設定済み" in captured.out

    def test_api_key_absent_is_reported_as_not_configured(self, tmp_path, monkeypatch, capsys):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        zip_path = _build_zip(tmp_path, entries=_valid_entries())

        main(["--zip", str(zip_path)])

        captured = capsys.readouterr()
        assert "未設定" in captured.out

    def test_api_key_value_never_appears_in_exception_text(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "dummy-secret-value")
        # 検査失敗（ZIPなし）を起こし、例外/結果の文字列表現にAPIキーが含まれないことを確認する。
        missing = tmp_path / "does_not_exist.zip"
        results = check_handoff_zip(missing)
        for name, _passed, detail in results:
            assert "dummy-secret-value" not in name
            assert "dummy-secret-value" not in detail


# ============================================================
# 副作用がないこと（展開しない・既存ファイルへ影響しない）
# ============================================================
class TestNoSideEffects:
    def test_zip_is_not_extracted_to_disk(self, tmp_path):
        zip_path = _build_zip(tmp_path, entries=_valid_entries())
        before = set(tmp_path.iterdir())

        check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))

        after = set(tmp_path.iterdir())
        assert before == after  # ZIP以外の新規ファイル・ディレクトリが作られていない

    def test_existing_unrelated_file_is_not_modified(self, tmp_path):
        sentinel = tmp_path / "unrelated_existing_file.txt"
        sentinel.write_text("original content", encoding="utf-8")
        zip_path = _build_zip(tmp_path, entries=_valid_entries())

        check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))

        assert sentinel.read_text(encoding="utf-8") == "original content"

    def test_main_does_not_create_any_output_file(self, tmp_path, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        zip_path = _build_zip(tmp_path, entries=_valid_entries())
        before = set(tmp_path.iterdir())

        main(["--zip", str(zip_path)])

        after = set(tmp_path.iterdir())
        assert before == after


# ============================================================
# 単一ラッパーフォルダ構造（2026-07-27追加）
#
# ここでのテストはすべて一般仕様として実装する（実ZIPの内容へ後付けで
# 合わせたものではない）。実ZIPの再検査は別途 --zip 引数で行う。
# ============================================================
def _wrapped_entries(
    *,
    wrapper: str,
    pdf_bytes: bytes = _SYNTHETIC_PDF_BYTES,
    manifest_scheme: str = "logical",
) -> dict:
    """単一ラッパー構造の合成ZIP中身を返す。

    manifest_scheme:
        "logical" -> SHA256SUMS.txtは論理ルート相対パス（ラッパー名を含まない）で記載する。
        "wrapper" -> SHA256SUMS.txtはラッパー込みパス（実エントリ名と同じ形式）で記載する。
    """
    pdf_digest = _sha256_hex(pdf_bytes)
    if manifest_scheme == "logical":
        readme_manifest_path = REQUIRED_README
        pdf_manifest_path = TARGET_PDF_ENTRY
    elif manifest_scheme == "wrapper":
        readme_manifest_path = f"{wrapper}/{REQUIRED_README}"
        pdf_manifest_path = f"{wrapper}/{TARGET_PDF_ENTRY}"
    else:
        raise ValueError(f"unknown manifest_scheme: {manifest_scheme!r}")

    sha256sums = f"{_readme_digest()}  {readme_manifest_path}\n{pdf_digest}  {pdf_manifest_path}\n"

    return {
        f"{wrapper}/{REQUIRED_README}": _DUMMY_README_TEXT,
        f"{wrapper}/{REQUIRED_SHA256SUMS}": sha256sums,
        f"{wrapper}/{TARGET_PDF_ENTRY}": pdf_bytes,
    }


class TestSingleWrapperStructureSucceeds:
    def test_wrapper_named_geo_mvp_handoff_succeeds(self, tmp_path):
        entries = _wrapped_entries(wrapper="geo_mvp_handoff")
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        assert all(passed for _n, passed, _d in results)

    def test_wrapper_with_arbitrary_name_succeeds(self, tmp_path):
        # ラッパー名を固定値 geo_mvp_handoff に限定しないことの確認。
        entries = _wrapped_entries(wrapper="some_other_folder_name_2026")
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        assert all(passed for _n, passed, _d in results)

    def test_wrapper_detection_is_reported_in_logical_root_structure_detail(self, tmp_path):
        entries = _wrapped_entries(wrapper="my_wrapper")
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        detail = _results_detail(results, "logical_root_structure")
        assert "my_wrapper" in detail

    def test_root_structure_is_reported_as_root_in_detail(self, tmp_path):
        zip_path = _build_zip(tmp_path, entries=_valid_entries())
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        detail = _results_detail(results, "logical_root_structure")
        assert detail == "root"


class TestManifestSchemeForWrapper:
    def test_logical_relative_manifest_scheme_succeeds(self, tmp_path):
        entries = _wrapped_entries(wrapper="wrapper_a", manifest_scheme="logical")
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        d = _results_dict(results)
        assert d["sha256sums_manifest_scheme_determined"] is True
        assert all(passed for _n, passed, _d in results)

    def test_wrapper_inclusive_manifest_scheme_succeeds(self, tmp_path):
        # 実装方針として、ラッパー込みパス方式のSHA256SUMS.txtも許容する。
        entries = _wrapped_entries(wrapper="wrapper_b", manifest_scheme="wrapper")
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))
        d = _results_dict(results)
        assert d["sha256sums_manifest_scheme_determined"] is True
        assert all(passed for _n, passed, _d in results)

    def test_mixed_manifest_scheme_fails(self, tmp_path):
        # SHA256SUMS.txt内で、あるエントリは論理相対パス、別のエントリはラッパー込みパスで
        # 記載されている（一部だけ方式が異なる）場合は、推測で採用せず失敗させる。
        wrapper = "wrapper_c"
        pdf_digest = _sha256_hex(_SYNTHETIC_PDF_BYTES)
        sha256sums = (
            f"{_readme_digest()}  {REQUIRED_README}\n"  # 論理相対パス
            f"{pdf_digest}  {wrapper}/{TARGET_PDF_ENTRY}\n"  # ラッパー込みパス
        )
        entries = {
            f"{wrapper}/{REQUIRED_README}": _DUMMY_README_TEXT,
            f"{wrapper}/{REQUIRED_SHA256SUMS}": sha256sums,
            f"{wrapper}/{TARGET_PDF_ENTRY}": _SYNTHETIC_PDF_BYTES,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["sha256sums_manifest_scheme_determined"] is False
        assert d["sha256sums_parseable"] is True  # 書式自体は解析できるが方式が曖昧


class TestMultipleTopLevelOrMixedStructures:
    def test_multiple_top_level_elements_are_treated_as_root_structure_and_fail(self, tmp_path):
        entries = {
            "folder_a/README.md": _DUMMY_README_TEXT,
            "folder_a/SHA256SUMS.txt": "dummy\n",
            "folder_a/data/phase6_received/SFA用紙.pdf": _SYNTHETIC_PDF_BYTES,
            "folder_b/extra.txt": b"unrelated",
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        # 複数トップレベル要素のため単一ラッパーとして認識されず、ルート直下構造として
        # 判定される（この合成ZIPには真のルート直下ファイルがないため不合格になる）。
        assert _results_detail(results, "logical_root_structure") == "root"
        assert d["readme_exists"] is False

    def test_root_level_file_mixed_with_wrapped_files_fails(self, tmp_path):
        entries = _wrapped_entries(wrapper="mixed_wrapper")
        entries["README.md"] = _DUMMY_README_TEXT  # ラッパーに包まれていない、ルート直下のファイル
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert _results_detail(results, "logical_root_structure") == "root"
        # ルート直下にSHA256SUMS.txtがないため不合格になる。
        assert d["sha256sums_exists"] is False


class TestDoubleWrapperIsNotAutoStripped:
    def test_double_nested_wrapper_is_not_recursively_removed(self, tmp_path):
        # README.md/SHA256SUMS.txtがラッパー直下ではなく、ラッパー配下のさらに1階層下
        # （wrapper/inner/...）にある場合、単一ラッパーとして認識してはならない。
        wrapper = "outer_wrapper"
        entries = {
            f"{wrapper}/inner/{REQUIRED_README}": _DUMMY_README_TEXT,
            f"{wrapper}/inner/{REQUIRED_SHA256SUMS}": (
                f"{_readme_digest()}  {REQUIRED_README}\n"
                f"{_sha256_hex(_SYNTHETIC_PDF_BYTES)}  {TARGET_PDF_ENTRY}\n"
            ),
            f"{wrapper}/inner/{TARGET_PDF_ENTRY}": _SYNTHETIC_PDF_BYTES,
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        # 第1要素は"outer_wrapper"で全エントリ一致するが、その直下にREADME.md/
        # SHA256SUMS.txtが存在しない（1階層下にある）ため、単一ラッパーとして
        # 認識されない。二重に除去して"inner"を新たなラッパーとして再試行しない。
        assert _results_detail(results, "logical_root_structure") == "root"
        assert d["readme_exists"] is False


class TestBasenameOnlyMatchIsNotAccepted:
    def test_bare_basename_pdf_does_not_satisfy_wrapper_pdf_requirement(self, tmp_path):
        # data/phase6_received/ 配下ではなく、ラッパー直下に裸のbasenameだけで
        # 対象PDFを置いても、単一ラッパーのPDF要件を満たしたことにしない。
        wrapper = "basename_test_wrapper"
        entries = {
            f"{wrapper}/{REQUIRED_README}": _DUMMY_README_TEXT,
            f"{wrapper}/{REQUIRED_SHA256SUMS}": (
                f"{_readme_digest()}  {REQUIRED_README}\n"
                f"{_sha256_hex(_SYNTHETIC_PDF_BYTES)}  SFA用紙.pdf\n"
            ),
            f"{wrapper}/SFA用紙.pdf": _SYNTHETIC_PDF_BYTES,  # basenameのみ、正しい相対パスではない
        }
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert _results_detail(results, "logical_root_structure") == "root"
        assert d["readme_exists"] is False  # ルート直下にもREADME.mdがないため不合格


class TestDangerousPathCheckRunsBeforePrefixStripping:
    def test_dangerous_entry_inside_wrapper_is_rejected_before_wrapper_detection(self, tmp_path):
        entries = _wrapped_entries(wrapper="danger_wrapper")
        entries["../evil_outside_wrapper"] = b"malicious"
        zip_path = _build_zip(tmp_path, entries=entries)
        results = check_handoff_zip(zip_path)
        d = _results_dict(results)
        assert d["zip_no_dangerous_paths"] is False
        # 危険なパスが見つかった時点で停止し、ラッパー検出以降の項目は一切実行されない。
        assert "logical_root_structure" not in d
        assert "readme_exists" not in d


class TestNoSideEffectsForWrappedZip:
    def test_wrapped_zip_check_does_not_extract_or_modify_anything(self, tmp_path):
        entries = _wrapped_entries(wrapper="side_effect_wrapper")
        zip_path = _build_zip(tmp_path, entries=entries)
        before = set(tmp_path.iterdir())

        check_handoff_zip(zip_path, expected_pdf_sha256=_sha256_hex(_SYNTHETIC_PDF_BYTES))

        after = set(tmp_path.iterdir())
        assert before == after


# ============================================================
# ヘルパー関数の直接テスト（結合テストでは到達不能な分岐の網羅用）
#
# _detect_single_wrapper_prefixは第1パス要素の完全一致（casefoldではない）で
# ラッパーを認識するため、単一ラッパーとして認識された後の論理パス集合で
# 重複・casefold衝突が生じるケースは、理論上は必ず生エントリ名の時点でも
# 重複・casefold衝突として検出され、zip_no_dangerous_pathsで先に不合格となる
# （同一の1つの文字列prefixを外した残りが衝突するなら、prefixを含めた全体文字列も
# 衝突するため）。そのため、完全なZIP統合テストではこの分岐（内部関数
# _find_duplicate_or_casefold_collisionsの衝突検出そのもの）を独立して
# 再現できない。ここでは対象の内部関数を直接呼び出して検証する。
# ============================================================
class TestLogicalCollisionHelperDirect:
    def test_duplicate_logical_paths_are_detected(self):
        collisions = _find_duplicate_or_casefold_collisions(["data/a.txt", "data/a.txt"])
        assert collisions
        assert collisions[0][1] == "duplicate_logical_path"

    def test_casefold_collision_between_different_logical_paths_is_detected(self):
        collisions = _find_duplicate_or_casefold_collisions(["data/A.txt", "data/a.txt"])
        assert collisions
        assert collisions[0][1] == "case_insensitive_collision_after_prefix_strip"

    def test_no_collision_for_distinct_paths(self):
        collisions = _find_duplicate_or_casefold_collisions(["data/a.txt", "data/b.txt"])
        assert collisions == []


class TestWrapperDetectionHelperDirect:
    def test_returns_none_for_empty_set(self):
        assert _detect_single_wrapper_prefix(set()) is None

    def test_returns_none_when_readme_missing_under_candidate(self):
        raw_names = {
            f"w/{REQUIRED_SHA256SUMS}",
            f"w/{TARGET_PDF_ENTRY}",
        }
        assert _detect_single_wrapper_prefix(raw_names) is None

    def test_returns_wrapper_name_when_all_conditions_met(self):
        raw_names = {
            f"w/{REQUIRED_README}",
            f"w/{REQUIRED_SHA256SUMS}",
            f"w/{TARGET_PDF_ENTRY}",
        }
        assert _detect_single_wrapper_prefix(raw_names) == "w"
