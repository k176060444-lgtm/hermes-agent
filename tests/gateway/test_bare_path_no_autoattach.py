"""Dispatch-site bare paths are text, not attachments (local patch 2026-09-25).

``BasePlatformAdapter._extract_response_content`` used to auto-attach any bare
local file path mentioned in prose via ``extract_local_files`` — so merely
*referencing* a file in a reply uploaded it to the chat (upstream issue class
#64661 / #20834). This local patch restricts the dispatch site to explicit
``MEDIA:<path>`` tags only; bare prose paths stay visible text and are never
attached. ``extract_local_files`` itself is kept (other callers unchanged).
"""

from gateway.platforms.base import BasePlatformAdapter


def test_bare_prose_path_is_not_attached_and_text_kept(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("x: 1\n")
    text = f"根因见 {f} 的 listeners 段"
    files, cleaned = BasePlatformAdapter._extract_media_tag_local_files(text)
    assert files == []
    assert str(f) in cleaned  # path stays visible text


def test_media_tag_path_is_attached_and_stripped(tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("x: 1\n")
    text = f"here you go MEDIA:{f} enjoy"
    files, cleaned = BasePlatformAdapter._extract_media_tag_local_files(text)
    assert files == [str(f)]
    assert "MEDIA:" not in cleaned
    assert str(f) not in cleaned


def test_media_tag_quoted_path_is_attached(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("hi\n")
    text = f'MEDIA:"{f}"'
    files, cleaned = BasePlatformAdapter._extract_media_tag_local_files(text)
    assert files == [str(f)]
    assert cleaned == ""


def test_media_tag_missing_file_is_skipped_but_stripped(tmp_path):
    text = f"see MEDIA:{tmp_path}/does-not-exist.yaml later"
    files, cleaned = BasePlatformAdapter._extract_media_tag_local_files(text)
    assert files == []
    assert "MEDIA:" not in cleaned


def test_media_tag_inside_code_span_is_untouched(tmp_path):
    f = tmp_path / "a.yaml"
    f.write_text("x: 1\n")
    text = f"example: `MEDIA:{f}` (documentation only)"
    files, cleaned = BasePlatformAdapter._extract_media_tag_local_files(text)
    assert files == []
    assert "MEDIA:" in cleaned  # docs preserved verbatim


def test_regex_no_bare_match_outside_media():
    pat = BasePlatformAdapter._MEDIA_TAG_ANY_PATH_RE
    assert pat.search("MEDIA:C:/tmp/a.yaml") is not None
    assert pat.search("just C:/tmp/a.yaml in prose") is None
