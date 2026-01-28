import json
from pathlib import Path

from agent0_scanner import detect_duplicates
from agent0_translator import (
    detect_language_heuristic,
    extract_headline_source,
    headline_needs_translation,
    translate_headline_json,
    translate_headline_md,
)
from agent0_ui import ArticleItem, filter_items, parse_selection
from agent0_utils import move_selected_files, move_to_processed


def test_duplicate_detection_case_insensitive(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    processed_dir = tmp_path / "processed"
    input_dir.mkdir()
    processed_dir.mkdir()
    file_a = input_dir / "01-Test.json"
    file_b = input_dir / "01-test.json"
    file_a.write_text("{}", encoding="utf-8")
    file_b.write_text("{}", encoding="utf-8")
    processed = processed_dir / "02-Already.json"
    processed.write_text("{}", encoding="utf-8")

    unique, duplicates, already = detect_duplicates([file_a, file_b], processed_dir)
    assert len(unique) == 1
    assert len(duplicates) == 1

    matching = input_dir / "02-Already.json"
    matching.write_text("{}", encoding="utf-8")
    unique, duplicates, already = detect_duplicates([matching], processed_dir)
    assert len(unique) == 0
    assert len(already) == 1


def test_json_headline_translation_writes_headline_en_gb_only(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "01-article.json"
    data = {
        "original_title": "Interés por ser taxista alcanza récord",
        "original_language": "es",
        "main_content_body": "Cuerpo del artículo.",
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def fake_call(*_args, **_kwargs):
        return "Taxi driver interest hits record"

    monkeypatch.setattr("agent0_translator.call_deepseek_chat", fake_call)
    result = translate_headline_json(path, api_key="test-key", dry_run=False)
    updated = json.loads(path.read_text(encoding="utf-8"))

    assert result.headline_en_gb == "Taxi driver interest hits record"
    assert updated["headline_en_gb"] == "Taxi driver interest hits record"
    assert updated["main_content_body"] == "Cuerpo del artículo."
    assert updated["original_title"] == "Interés por ser taxista alcanza récord"
    assert "agent0_translated_at" in updated
    assert "agent0_model" in updated
    assert updated["agent0_headline_source_field"] == "original_title"


def test_md_translation_updates_only_h1(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "01-article.md"
    content = "# Interés por ser taxista alcanza récord\n\nBody stays.\n"
    path.write_text(content, encoding="utf-8")

    def fake_call(*_args, **_kwargs):
        return "Taxi driver interest hits record"

    monkeypatch.setattr("agent0_translator.call_deepseek_chat", fake_call)
    translate_headline_md(path, api_key="test-key", dry_run=False)
    updated = path.read_text(encoding="utf-8")

    assert updated.startswith("# Taxi driver interest hits record")
    assert "Body stays." in updated
    sidecar = Path(str(path) + ".meta.json")
    assert sidecar.exists()
    meta = json.loads(sidecar.read_text(encoding="utf-8"))
    assert meta["headline_en_gb"] == "Taxi driver interest hits record"
    assert meta["agent0_headline_source_field"] == "md_h1"


def test_processed_move_preserves_relative_structure(tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    processed_dir = tmp_path / "processed"
    nested = input_dir / "2026-01" / "06"
    nested.mkdir(parents=True)
    file_path = nested / "01-article.json"
    file_path.write_text("{}", encoding="utf-8")

    dest = move_to_processed(file_path, input_dir, processed_dir)
    assert dest.exists()
    assert dest == processed_dir / "2026-01" / "06" / "01-article.json"


def test_handoff_failure_does_not_move_file(tmp_path: Path, monkeypatch) -> None:
    input_dir = tmp_path / "input"
    processed_dir = tmp_path / "processed"
    input_dir.mkdir()
    processed_dir.mkdir()
    file_path = input_dir / "01-article.json"
    file_path.write_text("{}", encoding="utf-8")
    successes = {file_path: False}

    moved = move_selected_files([file_path], input_dir, processed_dir, successes, dry_run=False)
    assert moved == []
    assert file_path.exists()


def test_headline_source_fallbacks(tmp_path: Path) -> None:
    path = tmp_path / "01-foo-bar.json"
    data = {"title": "Fallback title"}
    headline, source = extract_headline_source(data, path)
    assert headline == "Fallback title"
    assert source == "title"

    data = {"headline": "Alt headline"}
    headline, source = extract_headline_source(data, path)
    assert headline == "Alt headline"
    assert source == "headline"

    data = {"meta": {"title": "Meta title"}}
    headline, source = extract_headline_source(data, path)
    assert headline == "Meta title"
    assert source == "meta.title"

    data = {}
    headline, source = extract_headline_source(data, path)
    assert "foo bar" in headline
    assert source == "filename"


def test_language_detection_uses_hint_when_present() -> None:
    needs, lang, conf = headline_needs_translation("Test headline", "en", "x", "deepseek-chat")
    assert needs is False
    assert lang == "en"
    assert conf == 1.0

    needs, lang, conf = headline_needs_translation("Titular", "es", "x", "deepseek-chat")
    assert needs is True
    assert lang == "es"
    assert conf == 1.0


def test_language_detection_heuristic_es_ca_en() -> None:
    lang, _conf = detect_language_heuristic("El taxi de Barcelona")
    assert lang == "es"
    lang, _conf = detect_language_heuristic("Els taxis de Barcelona")
    assert lang == "ca"
    lang, _conf = detect_language_heuristic("Barcelona taxi demand rises")
    assert lang == "en"


def test_parse_selection_ranges_and_commas() -> None:
    selected = parse_selection("1,3,5-7", 10)
    assert selected == [1, 3, 5, 6, 7]


def test_ui_filtering_does_not_change_indices() -> None:
    items = [
        ArticleItem(1, "01", "a.json", "/a.json", "A", "A", "en", False, False),
        ArticleItem(2, "02", "b.json", "/b.json", "B", "B", "es", True, False),
        ArticleItem(3, "03", "c.json", "/c.json", "C", "C", "en", False, False),
    ]
    filtered = filter_items(items, "b", False)
    assert [item.index for item in filtered] == [2]


def test_translation_sets_headline_en_gb_even_when_no_translation_needed(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "01-article.json"
    data = {
        "original_title": "English headline",
        "original_language": "en",
        "main_content_body": "Body",
    }
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def fail_call(*_args, **_kwargs):
        raise AssertionError("LLM should not be called for English hint")

    monkeypatch.setattr("agent0_translator.call_deepseek_chat", fail_call)
    result = translate_headline_json(path, api_key="test-key", dry_run=False)
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert result.headline_en_gb == "English headline"
    assert updated["headline_en_gb"] == "English headline"
