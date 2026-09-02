"""Focused tests for the prototype PNG metadata collection form."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from config_prototype.gui.components.technique_forms.metadata import (
    PNGMetadataDraft,
    PNGMetadataForm,
)
from config_prototype.gui.components.technique_forms.metadata.png_metadata_form import (
    SUGGESTED_KEYWORDS,
)
from src.core.stego.metadata_handlers.png_handler import STANDARD_KEYWORDS


_APP: QApplication | None = None


def _app() -> QApplication:
    global _APP
    _APP = QApplication.instance() or QApplication([])
    return _APP


def test_png_form_builds_production_style_collection_cards() -> None:
    _app()
    parent = QWidget()
    form = PNGMetadataForm(parent=parent)

    assert form.parent() is parent
    assert list(form.standard_fields) == STANDARD_KEYWORDS
    assert len(form.standard_fields) == 6
    assert form.custom_rows == []
    assert form.custom_count_badge.text() == "0"
    assert form.standard_card.objectName() == "card"
    assert form.custom_card.objectName() == "card"
    assert form.add_card.objectName() == "card"
    assert form.scroll_area.objectName() == "fileListScroll"
    assert form.scroll_area.widgetResizable()
    assert form.add_button.objectName() == "SecondaryBtn"
    assert [
        form.add_keyword_combo.itemText(index)
        for index in range(form.add_keyword_combo.count())
    ] == SUGGESTED_KEYWORDS


def test_add_card_creates_a_custom_row_and_resets_the_combo() -> None:
    _app()
    form = PNGMetadataForm()
    form.add_keyword_combo.setEditText("Project Code")

    form.add_button.click()

    assert len(form.custom_rows) == 1
    assert form.custom_rows[0].get_keyword() == "Project Code"
    assert form.custom_rows[0].get_value() == ""
    assert form.custom_count_badge.text() == "1"
    assert form.add_keyword_combo.currentText() == ""


def test_custom_row_remove_signal_updates_collection_and_count() -> None:
    _app()
    form = PNGMetadataForm()
    first = form.add_custom_row("First", "1")
    second = form.add_custom_row("Second", "2")

    first.delete_button.click()

    assert form.custom_rows == [second]
    assert form.custom_count_badge.text() == "1"
    assert first.isHidden()


def test_remove_unknown_custom_row_does_not_change_collection() -> None:
    _app()
    first_form = PNGMetadataForm()
    second_form = PNGMetadataForm()
    existing = first_form.add_custom_row("Existing", "value")
    foreign = second_form.add_custom_row("Foreign", "value")

    first_form.remove_custom_row(foreign)

    assert first_form.custom_rows == [existing]
    assert first_form.custom_count_badge.text() == "1"


def test_load_draft_splits_standard_and_custom_entries() -> None:
    _app()
    form = PNGMetadataForm()
    source = PNGMetadataDraft(
        entries={
            "Title": "Hidden title",
            "Author": "Alice",
            "Project Code": "S2",
        }
    )

    form.load_draft(source)

    assert form.standard_fields["Title"].get_value() == "Hidden title"
    assert form.standard_fields["Author"].get_value() == "Alice"
    assert form.standard_fields["Description"].is_empty()
    assert len(form.custom_rows) == 1
    assert form.custom_rows[0].get_keyword() == "Project Code"
    assert form.custom_rows[0].get_value() == "S2"
    assert form.custom_count_badge.text() == "1"


def test_load_draft_replaces_existing_form_state() -> None:
    _app()
    form = PNGMetadataForm()
    form.standard_fields["Title"].set_value("Old")
    old_row = form.add_custom_row("Old Key", "Old value")

    form.load_draft(
        PNGMetadataDraft(
            entries={
                "Software": "SIENG2",
                "New Key": "New value",
            }
        )
    )

    assert form.standard_fields["Title"].is_empty()
    assert form.standard_fields["Software"].get_value() == "SIENG2"
    assert len(form.custom_rows) == 1
    assert form.custom_rows[0].get_keyword() == "New Key"
    assert old_row not in form.custom_rows


def test_export_draft_collects_only_usable_entries() -> None:
    _app()
    form = PNGMetadataForm()
    form.standard_fields["Title"].set_value("  Hidden title  ")
    form.standard_fields["Author"].set_value("   ")
    form.add_custom_row("  Project Code  ", "  S2  ")
    form.add_custom_row("", "orphan value")

    exported = form.export_draft()

    assert exported == PNGMetadataDraft(
        entries={
            "Title": "Hidden title",
            "Project Code": "S2",
        }
    )


def test_exported_draft_is_detached_from_form_and_source() -> None:
    _app()
    source = PNGMetadataDraft(entries={"Title": "Original"})
    form = PNGMetadataForm()
    form.load_draft(source)

    source.entries["Title"] = "Changed source"
    exported = form.export_draft()
    exported.entries["Title"] = "Changed export"

    assert form.standard_fields["Title"].get_value() == "Original"
    assert form.export_draft() == PNGMetadataDraft(
        entries={"Title": "Original"}
    )


def test_clear_all_resets_standard_and_custom_collection() -> None:
    _app()
    form = PNGMetadataForm()
    form.standard_fields["Copyright"].set_value("Copyright 2026")
    custom_row = form.add_custom_row("Secret", "TEST")

    form.clear_all()

    assert all(field.is_empty() for field in form.standard_fields.values())
    assert form.custom_rows == []
    assert form.custom_count_badge.text() == "0"
    assert custom_row.isHidden()
    assert form.export_draft() == PNGMetadataDraft()


def test_png_form_has_no_file_pipeline_or_backend_responsibilities() -> None:
    _app()
    form = PNGMetadataForm()

    assert not hasattr(form, "file_path")
    assert not hasattr(form, "handler")
    assert not hasattr(form, "pipeline_mode")
    assert not hasattr(form, "save_metadata")


def test_validation_requires_at_least_one_metadata_value(
    monkeypatch,
) -> None:
    _app()
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )
    form = PNGMetadataForm()

    assert not form.validate_draft()
    assert warnings == [
        (
            "Validation Error",
            "Please add at least one PNG metadata value.",
        )
    ]


def test_validation_accepts_standard_metadata_without_custom_rows(
    monkeypatch,
) -> None:
    _app()

    def fail_if_warning_is_shown(*_args) -> None:
        raise AssertionError("valid PNG metadata must not show a warning")

    monkeypatch.setattr(QMessageBox, "warning", fail_if_warning_is_shown)
    form = PNGMetadataForm()
    form.standard_fields["Title"].set_value("Hidden title")

    assert form.validate_draft()


def test_validation_rejects_an_empty_custom_keyword(monkeypatch) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    form = PNGMetadataForm()
    form.add_custom_row("", "orphan value")

    assert not form.validate_draft()
    assert warnings == [
        "Please enter a keyword for every custom metadata row."
    ]


def test_validation_rejects_an_empty_custom_value(monkeypatch) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    form = PNGMetadataForm()
    form.add_custom_row("Project Code", "   ")

    assert not form.validate_draft()
    assert warnings == [
        "Please enter a value for custom metadata keyword 'Project Code'."
    ]


def test_validation_rejects_a_standard_keyword_in_custom_rows(
    monkeypatch,
) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    form = PNGMetadataForm()
    form.add_custom_row("Title", "Hidden title")

    assert not form.validate_draft()
    assert warnings == [
        "'Title' is a standard metadata keyword. "
        "Use its Standard Metadata field instead."
    ]


def test_validation_rejects_duplicate_custom_keywords(monkeypatch) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    form = PNGMetadataForm()
    form.add_custom_row("Secret", "First")
    form.add_custom_row("Secret", "Second")

    assert not form.validate_draft()
    assert warnings == ["Metadata keyword 'Secret' is used more than once."]


def test_validation_rejects_keywords_outside_png_text_rules(
    monkeypatch,
) -> None:
    _app()
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    invalid_cases = [
        (
            "秘密",
            "Metadata keyword '秘密' must use Latin-1 characters.",
        ),
        (
            "Line\nBreak",
            "Metadata keyword 'Line\nBreak' contains characters "
            "not allowed by PNG.",
        ),
        (
            "Double  Space",
            "Metadata keyword 'Double  Space' cannot contain "
            "consecutive spaces.",
        ),
    ]

    for keyword, expected_warning in invalid_cases:
        form = PNGMetadataForm()
        form.add_custom_row(keyword, "value")
        warnings.clear()

        assert not form.validate_draft()
        assert warnings == [expected_warning]


def test_keyword_validation_uses_encoded_png_byte_limit() -> None:
    assert PNGMetadataForm.keyword_validation_error("K" * 79) is None
    assert PNGMetadataForm.keyword_validation_error("K" * 80) == (
        "PNG metadata keywords must be between 1 and 79 bytes."
    )


def test_validation_accepts_standard_and_valid_custom_metadata(
    monkeypatch,
) -> None:
    _app()

    def fail_if_warning_is_shown(*_args) -> None:
        raise AssertionError("valid PNG metadata must not show a warning")

    monkeypatch.setattr(QMessageBox, "warning", fail_if_warning_is_shown)
    form = PNGMetadataForm()
    form.standard_fields["Author"].set_value("Alice")
    form.add_custom_row("Project Code", "S2")
    form.add_custom_row("Café", "metadata")

    assert form.validate_draft()
